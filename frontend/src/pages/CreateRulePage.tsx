import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { rulesApi } from '../api/rules';
import { ConditionBuilder, type ConditionBuilderMode } from '../components/rules/ConditionBuilder';
import { IntentPatternPicker } from '../components/rules/IntentPatternPicker';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { JsonEditor } from '../components/ui/json-editor';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import type { ConditionGroup, RuleCreate } from '../types/rule';
import { toast } from 'sonner';
import { ChevronRight, ChevronLeft, Save, FlaskConical, PlusCircle, Check } from 'lucide-react';

const STEPS = ['Basic Info', 'Conditions', 'Action', 'Review & Save'];

const DEFAULT_TREE: ConditionGroup = { type: 'group', op: 'AND', children: [] };

export default function CreateRulePage() {
    const navigate = useNavigate();
    const [step, setStep] = useState(0);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [group, setGroup] = useState('');
    const [priority, setPriority] = useState(0);
    const [enabled, setEnabled] = useState(true);
    const [conditionTree, setConditionTree] = useState<ConditionGroup>(DEFAULT_TREE);
    const [dslJson, setDslJson] = useState('');
    const [dslError, setDslError] = useState('');
    const [actionName, setActionName] = useState('');
    const [actionParams, setActionParams] = useState('');
    const [testResult, setTestResult] = useState<string | null>(null);
    const [builderMode, setBuilderMode] = useState<ConditionBuilderMode>('legacy');
    const [intentPattern, setIntentPattern] = useState('');

    const { data: actionsData } = useQuery({
        queryKey: ['available-actions'],
        queryFn: () => rulesApi.availableActions().then((r) => r.data),
    });

    // Sync condition tree → JSON
    useEffect(() => {
        setDslJson(JSON.stringify(conditionTree, null, 2));
    }, [conditionTree]);

    const handleDslChange = (val: string) => {
        setDslJson(val);
        try {
            const parsed = JSON.parse(val);
            setConditionTree(parsed);
            setDslError('');
        } catch {
            setDslError('Invalid JSON');
        }
    };

    const buildPayload = (): RuleCreate => {
        let action = actionName;
        if (actionParams.trim()) {
            try {
                const params = JSON.parse(actionParams);
                action = JSON.stringify({ action: actionName, params });
            } catch { /* keep name only */ }
        }
        return {
            name: name.trim(),
            description: description.trim() || null,
            group: group.trim() || null,
            priority,
            enabled,
            condition_dsl: conditionTree,
            evaluation_mode: builderMode === 'stateful' ? 'stateful' : 'stateless',
            rule_metadata: builderMode === 'stateful'
                ? { intent_pattern: intentPattern.trim() || null, canonical_mapping: 'auto' }
                : undefined,
            action,
        };
    };

    const validateStep = () => {
        if (step === 0 && !name.trim()) { toast.error('Name is required'); return false; }
        if (step === 2 && !actionName) { toast.error('Please select an action'); return false; }
        return true;
    };

    const testMutation = useMutation({
        mutationFn: () => rulesApi.validate(buildPayload()),
        onSuccess: (res) => {
            const r = res.data;
            if (r.conflicts.length === 0 && r.similar_rules.length === 0) {
                setTestResult('✅ No conflicts found. Rule is ready to save!');
            } else if (r.conflicts.length > 0) {
                setTestResult(`⚠️ ${r.conflicts.length} conflict(s): ${r.conflicts.map((c) => c.description).join('; ')}`);
            } else {
                setTestResult(`ℹ️ ${r.similar_rules.length} similar rule(s) found. Review before saving.`);
            }
        },
        onError: () => setTestResult('❌ Validation failed'),
    });

    const createMutation = useMutation({
        mutationFn: () => rulesApi.create(buildPayload()),
        onSuccess: () => {
            toast.success('Rule created successfully!');
            navigate('/rules');
        },
        onError: (err: unknown) => {
            const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
            if (detail && typeof detail === 'object' && 'message' in detail) {
                toast.error((detail as { message: string }).message);
            } else {
                toast.error('Failed to create rule');
            }
        },
    });

    const categorized = actionsData?.categorized ?? {};
    const selectedActionDesc = actionsData?.actions.find((a) => a.name === actionName)?.description;

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            {/* Page header */}
            <div className="flex items-center gap-3 mb-8">
                <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-emerald-500/10">
                    <PlusCircle size={18} className="text-emerald-500" />
                </div>
                <h1 className="text-xl font-bold text-foreground">Create Rule</h1>
            </div>

            {/* Stepper — UI-only: modern pill-style stepper */}
            <div className="flex items-center mb-8 gap-1">
                {STEPS.map((s, i) => (
                    <div key={s} className="flex items-center">
                        <div className="flex items-center gap-2">
                            <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-200 ${i === step
                                    ? 'bg-primary text-white shadow-sm'
                                    : i < step
                                        ? 'bg-emerald-500 text-white'
                                        : 'bg-muted text-muted-foreground'
                                }`}>
                                {i < step ? <Check size={13} /> : i + 1}
                            </span>
                            <span className={`text-sm hidden sm:block transition-colors ${i === step ? 'text-foreground font-medium' : i < step ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'
                                }`}>{s}</span>
                        </div>
                        {i < STEPS.length - 1 && (
                            <div className={`w-8 h-px mx-2 transition-colors ${i < step ? 'bg-emerald-500/40' : 'bg-border'}`} />
                        )}
                    </div>
                ))}
            </div>

            {/* Step 0: Basic Info */}
            {step === 0 && (
                <div className="space-y-5 border border-border/50 rounded-xl p-6 bg-card/50 animate-fade-in">
                    <div>
                        <label className="text-sm font-medium text-foreground">Name *</label>
                        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="High Value Transaction Alert" className="mt-1.5" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-foreground">Description</label>
                        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1.5" rows={2} />
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <label className="text-sm font-medium text-foreground">Group</label>
                            <Input value={group} onChange={(e) => setGroup(e.target.value)} placeholder="fraud_detection" className="mt-1.5" />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-foreground">Priority</label>
                            <Input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="mt-1.5" />
                        </div>
                        <div className="flex items-end pb-1">
                            <label className="flex items-center gap-2.5 cursor-pointer">
                                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="w-4 h-4 rounded" />
                                <span className="text-sm font-medium text-foreground">Enabled</span>
                            </label>
                        </div>
                    </div>
                </div>
            )}

            {/* Step 1: Conditions */}
            {step === 1 && (
                <div className="border border-border/50 rounded-xl p-6 bg-card/50 animate-fade-in">
                    <Tabs defaultValue="visual">
                        <TabsList>
                            <TabsTrigger value="visual">Visual Builder</TabsTrigger>
                            <TabsTrigger value="json">JSON Editor</TabsTrigger>
                        </TabsList>
                        <TabsContent value="visual" className="mt-4">
                            <p className="text-xs text-muted-foreground mb-3">Build your conditions visually. Changes sync to JSON automatically.</p>
                            <ConditionBuilder
                                value={conditionTree}
                                onChange={setConditionTree}
                                mode={builderMode}
                                onModeChange={setBuilderMode}
                                statefulContent={(
                                    <div className="space-y-3">
                                        <div className="rounded-lg border border-blue-200/70 bg-blue-50/70 dark:border-blue-900/50 dark:bg-blue-950/20 p-3">
                                            <p className="text-xs text-blue-800 dark:text-blue-200">
                                                Stateful pattern mode generates canonical condition mapping automatically. The JSON editor remains available for inspection and advanced overrides.
                                            </p>
                                        </div>
                                        <IntentPatternPicker value={intentPattern} onChange={setIntentPattern} />
                                    </div>
                                )}
                            />
                        </TabsContent>
                        <TabsContent value="json" className="mt-4">
                            <p className="text-xs text-muted-foreground mb-3">Edit as JSON. Changes sync to the visual builder.</p>
                            <JsonEditor
                                value={dslJson}
                                onChange={handleDslChange}
                                height="250px"
                            />
                            {dslError && <p className="text-xs text-red-500 mt-1.5">{dslError}</p>}
                        </TabsContent>
                    </Tabs>
                </div>
            )}

            {/* Step 2: Action */}
            {step === 2 && (
                <div className="space-y-5 border border-border/50 rounded-xl p-6 bg-card/50 animate-fade-in">
                    <div>
                        <label className="text-sm font-medium text-foreground">Select Action *</label>
                        <select
                            value={actionName}
                            onChange={(e) => setActionName(e.target.value)}
                            className="native-select mt-1.5 w-full"
                        >
                            <option value="">-- Select an action --</option>
                            {Object.entries(categorized).map(([cat, actions]) => (
                                <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                                    {(actions as Array<{ name: string }>).map((a) => (
                                        <option key={a.name} value={a.name}>{a.name}</option>
                                    ))}
                                </optgroup>
                            ))}
                        </select>
                        {selectedActionDesc && <p className="text-xs text-muted-foreground mt-1.5">{selectedActionDesc}</p>}
                    </div>
                    <div>
                        <label className="text-sm font-medium text-foreground">Action Parameters (JSON, optional)</label>
                        <div className="mt-1.5">
                            <JsonEditor
                                value={actionParams}
                                onChange={(val) => setActionParams(val)}
                                height="120px"
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Step 3: Review */}
            {step === 3 && (
                <div className="space-y-4 animate-fade-in">
                    <div className="border border-border/50 rounded-xl p-6 bg-card/50">
                        <h3 className="font-semibold mb-3 text-foreground">Rule Preview</h3>
                        <pre className="json-pre">{JSON.stringify(buildPayload(), null, 2)}</pre>
                    </div>
                    {testResult && (
                        <div className={`p-4 rounded-xl text-sm border ${testResult.startsWith('✅') ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/15 dark:border-emerald-800/50' : testResult.startsWith('⚠️') ? 'bg-amber-50 border-amber-200 dark:bg-amber-900/15 dark:border-amber-800/50' : 'bg-red-50 border-red-200 dark:bg-red-900/15 dark:border-red-800/50'}`}>
                            {testResult}
                        </div>
                    )}
                </div>
            )}

            {/* Navigation */}
            <div className="flex items-center gap-3 mt-8 pt-5 border-t border-border/40 flex-wrap">
                {step > 0 && (
                    <Button variant="outline" onClick={() => setStep((s) => s - 1)}>
                        <ChevronLeft size={14} /> Back
                    </Button>
                )}
                {step < STEPS.length - 1 && (
                    <Button onClick={() => { if (validateStep()) setStep((s) => s + 1); }}>
                        Next <ChevronRight size={14} />
                    </Button>
                )}
                {step === STEPS.length - 1 && (
                    <>
                        <Button
                            variant="secondary"
                            onClick={() => testMutation.mutate()}
                            disabled={testMutation.isPending}
                        >
                            <FlaskConical size={14} /> {testMutation.isPending ? 'Testing…' : 'Test Rule'}
                        </Button>
                        <Button
                            onClick={() => createMutation.mutate()}
                            disabled={createMutation.isPending}
                        >
                            <Save size={14} /> {createMutation.isPending ? 'Saving…' : 'Save Rule'}
                        </Button>
                    </>
                )}
                <Button variant="ghost" onClick={() => navigate('/rules')}>Cancel</Button>
            </div>
        </div>
    );
}
