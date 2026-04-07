import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { rulesApi } from '../../api/rules';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { Spinner } from '../ui/spinner';
import { Upload, FileJson, CheckCircle, AlertTriangle } from 'lucide-react';

interface BulkImportResult {
    imported: number;
    errors?: Array<{ index: number; error: string }>;
    conflicts?: number;
}

export function BulkImportTab() {
    const [mode, setMode] = useState<'json' | 'file'>('json');
    const [jsonText, setJsonText] = useState('');
    const [validateConflicts, setValidateConflicts] = useState(true);
    const [result, setResult] = useState<BulkImportResult | null>(null);
    const queryClient = useQueryClient();

    const jsonMutation = useMutation({
        mutationFn: (rulesOverride: unknown[] | undefined) => {
            const rules = rulesOverride ?? JSON.parse(jsonText);
            if (!Array.isArray(rules)) throw new Error('Expected a JSON array of rules');
            return rulesApi.bulkImport(rules, validateConflicts).then((r) => r.data);
        },
        onSuccess: (data) => {
            setResult(data);
            toast.success(`Imported ${data.imported ?? 0} rule(s)`);
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        },
        onError: (err: unknown) => {
            const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
                ?.response?.data?.detail ?? (err as Error).message ?? 'Import failed';
            toast.error(msg);
        },
    });

    const fileMutation = useMutation({
        mutationFn: (file: File) => rulesApi.bulkUpload(file, validateConflicts).then((r) => r.data),
        onSuccess: (data) => {
            setResult(data);
            toast.success(`Imported ${data.imported ?? 0} rule(s)`);
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        },
        onError: (err: unknown) => {
            const msg = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail ?? 'Upload failed';
            toast.error(msg);
        },
    });

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const name = file.name.toLowerCase();
        if (name.endsWith('.json')) {
            // JSON files: read content, parse, and use the JSON bulk import endpoint
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const text = reader.result as string;
                    const rules = JSON.parse(text);
                    if (!Array.isArray(rules)) {
                        toast.error('JSON file must contain an array of rules');
                        return;
                    }
                    jsonMutation.mutate(rules);
                } catch {
                    toast.error('Invalid JSON in file');
                }
            };
            reader.readAsText(file);
        } else {
            // CSV / XLSX files: upload via multipart form-data
            fileMutation.mutate(file);
        }
    };

    const isPending = jsonMutation.isPending || fileMutation.isPending;

    return (
        <div>
            <h2 className="font-semibold mb-5 text-foreground">Bulk Import</h2>

            {/* Mode toggle */}
            <div className="flex gap-2 mb-5">
                <Button
                    size="sm"
                    variant={mode === 'json' ? 'default' : 'outline'}
                    onClick={() => setMode('json')}
                >
                    <FileJson size={14} /> JSON Paste
                </Button>
                <Button
                    size="sm"
                    variant={mode === 'file' ? 'default' : 'outline'}
                    onClick={() => setMode('file')}
                >
                    <Upload size={14} /> File Upload
                </Button>
            </div>

            {/* Options */}
            <div className="flex items-center gap-2.5 mb-5">
                <input
                    type="checkbox"
                    id="validate-conflicts"
                    checked={validateConflicts}
                    onChange={(e) => setValidateConflicts(e.target.checked)}
                    className="h-4 w-4 rounded"
                />
                <label htmlFor="validate-conflicts" className="text-sm text-foreground">
                    Validate conflicts before import
                </label>
            </div>

            {mode === 'json' ? (
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        Paste a JSON array of rule objects below.
                    </p>
                    <Textarea
                        value={jsonText}
                        onChange={(e) => setJsonText(e.target.value)}
                        rows={12}
                        className="font-mono text-xs"
                        placeholder={`[\n  {\n    "name": "My Rule",\n    "condition_dsl": { "type": "group", "op": "AND", "children": [] },\n    "action": "log"\n  }\n]`}
                    />
                    <Button
                        onClick={() => jsonMutation.mutate(undefined)}
                        disabled={isPending || !jsonText.trim()}
                    >
                        {jsonMutation.isPending ? <Spinner size="sm" className="mr-1" /> : null}
                        Import Rules
                    </Button>
                </div>
            ) : (
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        Upload a JSON, CSV, or Excel (.xlsx) file containing rule data.
                    </p>
                    <div className="border-2 border-dashed border-border/60 rounded-xl p-10 text-center bg-muted/10 hover:bg-muted/20 transition-colors">
                        <Upload size={32} className="mx-auto text-muted-foreground/40 mb-3" />
                        <label className="cursor-pointer">
                            <span className="text-primary font-medium hover:underline">
                                Choose a file
                            </span>
                            <input
                                type="file"
                                accept=".json,.csv,.xlsx,.xls"
                                onChange={handleFileSelect}
                                className="hidden"
                                disabled={isPending}
                            />
                        </label>
                        <p className="text-xs text-muted-foreground mt-1.5">.json, .csv, .xlsx files supported</p>
                    </div>
                    {fileMutation.isPending && (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Spinner size="sm" /> Uploading…
                        </div>
                    )}
                </div>
            )}

            {/* Results — UI-only: refined result panel */}
            {result && (
                <div className="mt-6 border border-border/50 rounded-xl p-5 space-y-3 bg-card/50 animate-fade-in">
                    <div className="flex items-center gap-2">
                        <CheckCircle size={18} className="text-emerald-500" />
                        <span className="font-semibold text-sm text-foreground">
                            Import Complete — {result.imported} rule(s) imported
                        </span>
                    </div>
                    {(result.conflicts ?? 0) > 0 && (
                        <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 text-sm">
                            <AlertTriangle size={14} />
                            {result.conflicts} conflict(s) detected — check the Conflicts page.
                        </div>
                    )}
                    {result.errors && result.errors.length > 0 && (
                        <div>
                            <p className="text-sm font-medium text-red-600 dark:text-red-400 mb-1.5">
                                {result.errors.length} error(s):
                            </p>
                            <div className="max-h-40 overflow-auto text-xs font-mono bg-muted/40 rounded-lg p-3">
                                {result.errors.map((err, i) => (
                                    <div key={i}>Row {err.index}: {err.error}</div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
