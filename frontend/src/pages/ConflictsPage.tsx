import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { rulesApi } from '../api/rules';
import { getConflictTypeConfig } from '../types/conflict';
import type { ConflictedRule, ConflictStatus } from '../types/conflict';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Spinner } from '../components/ui/spinner';
import { EmptyState } from '../components/ui/empty-state';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { AlertTriangle, RefreshCw, CheckCircle, XCircle, Eye, GitCompare, Edit, Trash2 } from 'lucide-react';
import { formatDate, escapeHtml } from '../lib/utils';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import {
    AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader,
    AlertDialogTitle, AlertDialogDescription, AlertDialogFooter,
    AlertDialogAction, AlertDialogCancel,
} from '../components/ui/alert-dialog';

const STATUS_OPTIONS: { label: string; value: ConflictStatus }[] = [
    { label: 'All', value: '' },
    { label: 'Pending', value: 'pending' },
    { label: 'Approved', value: 'approved' },
    { label: 'Dismissed', value: 'dismissed' },
];

/* ─── Recursive JSON diff logic (ported from fielddiff.js) ─── */
interface DiffEntry {
    path: string[];
    valueA: unknown;
    valueB: unknown;
    type: 'unchanged' | 'changed' | 'added' | 'removed';
}

function diffJson(a: unknown, b: unknown, path: string[] = []): DiffEntry[] {
    if (typeof a !== typeof b) {
        return [{ path, valueA: a, valueB: b, type: 'changed' }];
    }
    if (typeof a !== 'object' || a === null || b === null) {
        if (a === b) return [{ path, valueA: a, valueB: b, type: 'unchanged' }];
        return [{ path, valueA: a, valueB: b, type: 'changed' }];
    }
    const aObj = a as Record<string, unknown>;
    const bObj = b as Record<string, unknown>;
    const keys = new Set([...Object.keys(aObj), ...Object.keys(bObj)]);
    let diffs: DiffEntry[] = [];
    for (const key of keys) {
        if (!(key in aObj)) {
            diffs.push({ path: [...path, key], valueA: undefined, valueB: bObj[key], type: 'added' });
        } else if (!(key in bObj)) {
            diffs.push({ path: [...path, key], valueA: aObj[key], valueB: undefined, type: 'removed' });
        } else {
            diffs = diffs.concat(diffJson(aObj[key], bObj[key], [...path, key]));
        }
    }
    return diffs;
}

function formatDiffValue(v: unknown): string {
    if (v === undefined) return 'undefined';
    if (v === null) return 'null';
    if (typeof v === 'object') return JSON.stringify(v, null, 2);
    return String(v);
}

/* ─── Side-by-side Rule Compare Modal ─── */
function RuleCompareModal({
    conflict,
    onClose,
}: {
    conflict: ConflictedRule;
    onClose: () => void;
}) {
    const ruleId = conflict.conflicting_rule_id;

    const { data: ruleB, isLoading, error } = useQuery({
        queryKey: ['rule', ruleId],
        queryFn: () => rulesApi.get(ruleId!).then((r) => r.data),
        enabled: !!ruleId,
    });

    // Build ruleA from the conflict record
    const ruleA = useMemo(() => ({
        id: `parked-${conflict.id}`,
        name: conflict.name,
        description: conflict.description ?? '',
        group: conflict.group ?? '',
        priority: conflict.priority,
        enabled: conflict.enabled,
        condition_dsl: conflict.condition_dsl,
        action: conflict.action,
    }), [conflict]);

    // Compute diff entries grouped by top-level field
    const groupedDiffs = useMemo(() => {
        if (!ruleB) return null;
        const bObj = {
            id: ruleB.id,
            name: ruleB.name,
            description: ruleB.description ?? '',
            group: ruleB.group ?? '',
            priority: ruleB.priority,
            enabled: ruleB.enabled,
            condition_dsl: ruleB.condition_dsl,
            action: ruleB.action,
        };
        const diffs = diffJson(ruleA, bObj);
        const groups: Record<string, DiffEntry[]> = {};
        for (const d of diffs) {
            const top = d.path[0] ?? '(root)';
            if (!groups[top]) groups[top] = [];
            groups[top].push(d);
        }
        return groups;
    }, [ruleA, ruleB]);

    const hasChanges = groupedDiffs
        ? Object.values(groupedDiffs).flat().some((d) => d.type !== 'unchanged')
        : false;

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <GitCompare size={18} className="text-primary" />
                        Side-by-Side Rule Comparison
                    </DialogTitle>
                </DialogHeader>

                {isLoading && (
                    <div className="flex items-center justify-center py-12">
                        <Spinner size="lg" />
                    </div>
                )}

                {error && (
                    <div className="text-center py-8">
                        <p className="text-destructive text-sm font-medium">
                            Failed to load conflicting rule (ID: {ruleId}).
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                            The rule may have been deleted.
                        </p>
                    </div>
                )}

                {groupedDiffs && ruleB && (
                    <div className="flex-1 overflow-y-auto -mx-6 px-6">
                        {/* Column headers */}
                        <div className="grid grid-cols-2 gap-4 mb-3 sticky top-0 bg-card z-10 pb-2 border-b border-border/40">
                            <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                                <span className="inline-block w-3 h-3 rounded-sm bg-amber-400/60" />
                                Parked Rule: <span className="text-primary truncate">{conflict.name}</span>
                            </div>
                            <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                                <span className="inline-block w-3 h-3 rounded-sm bg-blue-400/60" />
                                Existing Rule: <span className="text-primary truncate">{ruleB.name}</span>
                            </div>
                        </div>

                        {!hasChanges && (
                            <div className="text-center py-6 text-muted-foreground text-sm">
                                <CheckCircle size={24} className="mx-auto mb-2 text-emerald-500" />
                                Both rules are identical.
                            </div>
                        )}

                        {/* Diff rows grouped by top-level field */}
                        <div className="space-y-2">
                            {Object.entries(groupedDiffs).map(([field, entries]) => {
                                const allUnchanged = entries.every((e) => e.type === 'unchanged');
                                return (
                                    <details key={field} open={!allUnchanged} className="group/diff">
                                        <summary
                                            className={`cursor-pointer flex items-center gap-2 text-xs font-semibold uppercase tracking-wider py-1.5 px-2 rounded-md transition-colors select-none ${allUnchanged
                                                ? 'text-muted-foreground/60 hover:text-muted-foreground'
                                                : 'text-foreground bg-amber-50 dark:bg-amber-900/10'
                                                }`}
                                        >
                                            {!allUnchanged && <span className="text-amber-500">●</span>}
                                            {field}
                                        </summary>
                                        <div className="grid grid-cols-2 gap-4 mt-1 mb-2">
                                            {entries.map((entry, i) => {
                                                const key = entry.path.slice(1).join('.') || field;
                                                const valA = formatDiffValue(entry.valueA);
                                                const valB = formatDiffValue(entry.valueB);

                                                const bgA =
                                                    entry.type === 'changed' ? 'bg-red-50 dark:bg-red-950/30 border-l-2 border-l-red-400' :
                                                        entry.type === 'removed' ? 'bg-red-50 dark:bg-red-950/30 border-l-2 border-l-red-400' :
                                                            entry.type === 'added' ? 'bg-muted/30' :
                                                                '';
                                                const bgB =
                                                    entry.type === 'changed' ? 'bg-emerald-50 dark:bg-emerald-950/30 border-l-2 border-l-emerald-400' :
                                                        entry.type === 'added' ? 'bg-emerald-50 dark:bg-emerald-950/30 border-l-2 border-l-emerald-400' :
                                                            entry.type === 'removed' ? 'bg-muted/30' :
                                                                '';

                                                return (
                                                    <React.Fragment key={i}>
                                                        <div className={`rounded-md p-2 text-xs font-mono ${bgA}`}>
                                                            <span className="text-muted-foreground font-sans text-2xs">{key}: </span>
                                                            <pre className="whitespace-pre-wrap break-words text-foreground mt-0.5">{escapeHtml(valA)}</pre>
                                                        </div>
                                                        <div className={`rounded-md p-2 text-xs font-mono ${bgB}`}>
                                                            <span className="text-muted-foreground font-sans text-2xs">{key}: </span>
                                                            <pre className="whitespace-pre-wrap break-words text-foreground mt-0.5">{escapeHtml(valB)}</pre>
                                                        </div>
                                                    </React.Fragment>
                                                );
                                            })}
                                        </div>
                                    </details>
                                );
                            })}
                        </div>
                    </div>
                )}

                <div className="flex justify-end mt-3 pt-3 border-t border-border/40">
                    <Button variant="outline" size="sm" onClick={onClose}>
                        Close
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

/* ─── Edit & Resolve Modal ─── */
function ResolveEditorModal({
    conflict,
    onClose,
    onResolved,
}: {
    conflict: ConflictedRule;
    onClose: () => void;
    onResolved: () => void;
}) {
    const conditionObj = useMemo(() => {
        if (typeof conflict.condition_dsl === 'string') {
            try { return JSON.parse(conflict.condition_dsl); } catch { return conflict.condition_dsl; }
        }
        return conflict.condition_dsl;
    }, [conflict]);

    const [name, setName] = useState(conflict.name);
    const [description, setDescription] = useState(conflict.description ?? '');
    const [group, setGroup] = useState(conflict.group ?? '');
    const [priority, setPriority] = useState(conflict.priority);
    const [action, setAction] = useState(conflict.action ?? '');
    const [conditionJson, setConditionJson] = useState(JSON.stringify(conditionObj, null, 2));
    const [jsonError, setJsonError] = useState('');

    const { data: actionsData } = useQuery({
        queryKey: ['available-actions'],
        queryFn: () => rulesApi.availableActions().then((r) => r.data),
        staleTime: 300_000,
    });

    const { data: groupsData } = useQuery({
        queryKey: ['rule-groups'],
        queryFn: () => rulesApi.groups().then((r) => r.data.groups),
        staleTime: 60_000,
    });

    const categorized = actionsData?.categorized ?? {};
    const selectedActionDesc = actionsData?.actions.find((a) => a.name === action)?.description;

    const resolveMutation = useMutation({
        mutationFn: () => {
            let parsedCondition: object;
            try {
                parsedCondition = JSON.parse(conditionJson);
            } catch {
                throw new Error('Invalid JSON in Condition DSL');
            }
            const body = {
                name: name.trim(),
                description: description.trim() || null,
                group: group.trim() || null,
                priority: isNaN(priority) ? 0 : priority,
                enabled: true,
                condition_dsl: parsedCondition,
                action: action.trim(),
            };
            return rulesApi.resolveConflict(conflict.id, body as Parameters<typeof rulesApi.resolveConflict>[1]);
        },
        onSuccess: (res) => {
            const msg = res.data?.message || 'Conflict resolved and rule created!';
            toast.success(msg);
            onResolved();
            onClose();
        },
        onError: (err: unknown) => {
            const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
            if (err instanceof Error && err.message === 'Invalid JSON in Condition DSL') {
                setJsonError('Invalid JSON in Condition DSL. Please fix and try again.');
                return;
            }
            if (detail && typeof detail === 'object' && 'message' in detail) {
                const d = detail as { message: string; conflicts?: Array<{ description?: string; type?: string }> };
                let msg = d.message;
                if (d.conflicts?.length) {
                    msg += ' — ' + d.conflicts.map(c => c.description || c.type).join('; ');
                }
                toast.error(msg);
            } else if (typeof detail === 'string') {
                toast.error(detail);
            } else {
                toast.error('Failed to resolve conflict');
            }
        },
    });

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Edit size={18} className="text-primary" />
                        Edit &amp; Resolve Conflict
                    </DialogTitle>
                </DialogHeader>

                <p className="text-sm text-muted-foreground mb-4">
                    Modify the <strong>priority</strong>, <strong>group</strong>, <strong>condition</strong>, or <strong>action</strong> to resolve the conflict.
                    Unchanged rules cannot be created.
                </p>

                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="text-sm font-medium text-foreground">Name</label>
                            <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-foreground">Group</label>
                            <select
                                value={group}
                                onChange={(e) => setGroup(e.target.value)}
                                className="native-select mt-1 w-full"
                            >
                                <option value="">— No group —</option>
                                {groupsData?.map((g) => (
                                    <option key={g} value={g}>{g}</option>
                                ))}
                                {group && !groupsData?.includes(group) && (
                                    <option value={group}>{group}</option>
                                )}
                            </select>
                        </div>
                        <div>
                            <label className="text-sm font-medium text-destructive">Priority ⚡</label>
                            <Input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="mt-1" />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-foreground">Action</label>
                            <select
                                value={action}
                                onChange={(e) => setAction(e.target.value)}
                                className="native-select mt-1 w-full"
                            >
                                <option value="">— Select an action —</option>
                                {Object.entries(categorized).map(([cat, actions]) => (
                                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                                        {(actions as Array<{ name: string }>).map((a) => (
                                            <option key={a.name} value={a.name}>{a.name}</option>
                                        ))}
                                    </optgroup>
                                ))}
                                {action && !actionsData?.actions.find((a) => a.name === action) && (
                                    <option value={action}>{action} (current)</option>
                                )}
                            </select>
                            {selectedActionDesc && (
                                <p className="text-xs text-muted-foreground mt-1">{selectedActionDesc}</p>
                            )}
                        </div>
                    </div>
                    <div>
                        <label className="text-sm font-medium text-foreground">Description</label>
                        <Input value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-foreground">Condition DSL (JSON)</label>
                        <Textarea
                            value={conditionJson}
                            onChange={(e) => {
                                setConditionJson(e.target.value);
                                setJsonError('');
                            }}
                            rows={8}
                            className="mt-1 font-mono text-xs"
                        />
                        {jsonError && <p className="text-xs text-destructive mt-1">{jsonError}</p>}
                    </div>
                </div>

                <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-border/40">
                    <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
                    <Button
                        size="sm"
                        onClick={() => resolveMutation.mutate()}
                        disabled={resolveMutation.isPending}
                    >
                        {resolveMutation.isPending ? <Spinner size="sm" className="mr-1" /> : null}
                        💾 Submit Resolved Rule
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

/* ─── Conflict Detail Modal ─── */
function ConflictDetailModal({
    conflict,
    onClose,
    onDismiss,
    dismissing,
    onCompare,
    onResolve,
    onDelete,
    deleting,
}: {
    conflict: ConflictedRule;
    onClose: () => void;
    onDismiss: (id: number) => void;
    dismissing: boolean;
    onCompare: (c: ConflictedRule) => void;
    onResolve: (c: ConflictedRule) => void;
    onDelete: (id: number) => void;
    deleting: boolean;
}) {
    const cfg = getConflictTypeConfig(conflict.conflict_type);

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <AlertTriangle size={18} style={{ color: cfg.color }} />
                        Conflict Detail
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 mt-2">
                    <div
                        className="rounded-xl p-3.5 text-sm border"
                        style={{
                            background: cfg.bgColor,
                            borderColor: cfg.borderColor,
                            color: cfg.color,
                        }}
                    >
                        <span className="font-semibold">{cfg.label}</span>
                        {cfg.description && <span className="ml-2 opacity-80">{cfg.description}</span>}
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Rule Name</div>
                            <div className="font-medium text-foreground">{conflict.name}</div>
                        </div>
                        <div>
                            <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Priority</div>
                            <div className="text-foreground">{conflict.priority}</div>
                        </div>
                        <div>
                            <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Group</div>
                            <div className="text-foreground">{conflict.group ?? '—'}</div>
                        </div>
                        <div>
                            <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Status</div>
                            <div className="capitalize text-foreground">{conflict.status}</div>
                        </div>
                        {conflict.conflicting_rule_name && (
                            <div className="col-span-2">
                                <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Conflicting With</div>
                                <div className="text-foreground">{conflict.conflicting_rule_name} (ID: {conflict.conflicting_rule_id})</div>
                            </div>
                        )}
                        <div className="col-span-2">
                            <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Conflict Description</div>
                            <div className="text-sm leading-relaxed text-foreground">{conflict.conflict_description}</div>
                        </div>
                        {conflict.review_notes && (
                            <div className="col-span-2">
                                <div className="text-muted-foreground text-[0.6875rem] uppercase tracking-wider mb-0.5">Review Notes</div>
                                <div className="text-sm leading-relaxed text-foreground">{conflict.review_notes}</div>
                            </div>
                        )}
                    </div>

                    <div className="text-xs text-muted-foreground border-t border-border/40 pt-3">
                        Submitted: {formatDate(conflict.submitted_at)}
                        {conflict.reviewed_at && <span className="ml-3">Reviewed: {formatDate(conflict.reviewed_at)}</span>}
                    </div>
                </div>

                <div className="flex justify-end gap-2 mt-2 flex-wrap">
                    {conflict.conflicting_rule_id && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onCompare(conflict)}
                            title={
                                !conflict.conflicting_rule_name
                                    ? 'Referenced rule may have been deleted'
                                    : 'Compare rules side by side'
                            }
                        >
                            <GitCompare size={14} className="mr-1" />
                            Compare
                        </Button>
                    )}
                    {conflict.status === 'pending' && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                                onClose();
                                onResolve(conflict);
                            }}
                        >
                            <Edit size={14} className="mr-1" />
                            Edit &amp; Resolve
                        </Button>
                    )}
                    {conflict.status === 'pending' && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onDismiss(conflict.id)}
                            disabled={dismissing}
                        >
                            {dismissing ? <Spinner size="sm" className="mr-1" /> : <XCircle size={14} className="mr-1" />}
                            Dismiss
                        </Button>
                    )}
                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button
                                variant="outline"
                                size="sm"
                                className="text-destructive hover:bg-destructive/10"
                                disabled={deleting}
                            >
                                {deleting ? <Spinner size="sm" className="mr-1" /> : <Trash2 size={14} className="mr-1" />}
                                Delete
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Delete parked rule "{conflict.name}"?</AlertDialogTitle>
                                <AlertDialogDescription>This will permanently delete this parked conflict rule. This action cannot be undone.</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => onDelete(conflict.id)}>Delete</AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                    <Button variant="ghost" size="sm" onClick={onClose}>
                        Close
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

export default function ConflictsPage() {
    const [statusFilter, setStatusFilter] = useState<ConflictStatus>('');
    const [selected, setSelected] = useState<ConflictedRule | null>(null);
    const [comparing, setComparing] = useState<ConflictedRule | null>(null);
    const [resolving, setResolving] = useState<ConflictedRule | null>(null);
    const queryClient = useQueryClient();

    const { data: conflicts, isLoading, refetch, isFetching } = useQuery<ConflictedRule[]>({
        queryKey: ['conflicts', statusFilter],
        queryFn: () => rulesApi.parkedConflicts(statusFilter || undefined).then((r) => r.data),
        staleTime: 30_000,
    });

    const dismissMutation = useMutation({
        mutationFn: (id: number) => rulesApi.dismissConflict(id, 'Dismissed via UI'),
        onSuccess: () => {
            toast.success('Conflict dismissed');
            setSelected(null);
            queryClient.invalidateQueries({ queryKey: ['conflicts'] });
        },
        onError: () => toast.error('Failed to dismiss conflict'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => rulesApi.deleteConflict(id),
        onSuccess: () => {
            toast.success('Parked rule deleted');
            setSelected(null);
            queryClient.invalidateQueries({ queryKey: ['conflicts'] });
        },
        onError: () => toast.error('Failed to delete parked rule'),
    });

    const statusCounts = {
        pending: conflicts?.filter((c) => c.status === 'pending').length ?? 0,
        approved: conflicts?.filter((c) => c.status === 'approved').length ?? 0,
        dismissed: conflicts?.filter((c) => c.status === 'dismissed').length ?? 0,
    };

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-amber-500/10">
                        <AlertTriangle size={18} className="text-amber-500" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-foreground">Conflicts</h1>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            Parked rule conflicts awaiting review
                        </p>
                    </div>
                </div>
                <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                    <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
                    Refresh
                </Button>
            </div>

            {/* Summary Cards — UI-only: refined stat cards */}
            <div className="grid grid-cols-3 gap-3 mb-6">
                <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
                    <div className="text-2xl font-bold text-amber-500">{statusCounts.pending}</div>
                    <div className="text-[0.6875rem] text-muted-foreground mt-1 font-medium uppercase tracking-wider">Pending</div>
                </div>
                <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
                    <div className="text-2xl font-bold text-emerald-500">{statusCounts.approved}</div>
                    <div className="text-[0.6875rem] text-muted-foreground mt-1 font-medium uppercase tracking-wider">Approved</div>
                </div>
                <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
                    <div className="text-2xl font-bold text-muted-foreground">{statusCounts.dismissed}</div>
                    <div className="text-[0.6875rem] text-muted-foreground mt-1 font-medium uppercase tracking-wider">Dismissed</div>
                </div>
            </div>

            {/* Status Filter Tabs */}
            <div className="flex gap-1 mb-6 border-b border-border">
                {STATUS_OPTIONS.map((opt) => (
                    <button
                        key={opt.value}
                        onClick={() => setStatusFilter(opt.value)}
                        className={`px-4 py-2.5 text-sm font-medium transition-all duration-150 border-b-2 -mb-px rounded-t-lg ${statusFilter === opt.value
                            ? 'border-primary text-primary bg-primary/5 dark:bg-primary/10'
                            : 'border-transparent text-foreground/60 hover:text-foreground hover:bg-muted/40'
                            }`}
                    >
                        {opt.label}
                        {opt.value === 'pending' && statusCounts.pending > 0 && (
                            <span className="ml-1.5 text-[0.6875rem] bg-amber-100/80 text-amber-700 dark:bg-amber-900/25 dark:text-amber-400 rounded-full px-1.5 py-0.5">
                                {statusCounts.pending}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {/* Loading */}
            {isLoading && (
                <div className="flex items-center justify-center py-16">
                    <Spinner size="lg" />
                </div>
            )}

            {/* Empty */}
            {!isLoading && !conflicts?.length && (
                <EmptyState
                    icon={<CheckCircle size={48} />}
                    title="No conflicts found"
                    description={statusFilter ? `No ${statusFilter} conflicts to display.` : 'All clear! No parked conflicts exist.'}
                />
            )}

            {/* Conflicts Table — UI-only: rounded-xl, softer borders */}
            {!isLoading && conflicts && conflicts.length > 0 && (
                <div className="overflow-x-auto rounded-xl border border-border/50 bg-card">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/20">
                            <tr>
                                {['Rule', 'Type', 'Group', 'Priority', 'Conflicting With', 'Status', 'Submitted', ''].map((h) => (
                                    <th key={h} className="text-left py-3 px-3.5 text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {conflicts.map((c) => {
                                const cfg = getConflictTypeConfig(c.conflict_type);
                                return (
                                    <tr
                                        key={c.id}
                                        className="border-t border-border/30 hover:bg-muted/20 transition-colors"
                                    >
                                        <td className="py-3 px-3.5 font-medium max-w-[160px] truncate text-foreground">{c.name}</td>
                                        <td className="py-3 px-3.5">
                                            <span
                                                className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border"
                                                style={{
                                                    color: cfg.color,
                                                    background: cfg.bgColor,
                                                    borderColor: cfg.borderColor,
                                                }}
                                            >
                                                {cfg.label}
                                            </span>
                                        </td>
                                        <td className="py-3 px-3.5 text-muted-foreground">{c.group ?? '—'}</td>
                                        <td className="py-3 px-3.5">{c.priority}</td>
                                        <td className="py-3 px-3.5 text-muted-foreground max-w-[120px] truncate">
                                            {c.conflicting_rule_name ?? '—'}
                                        </td>
                                        <td className="py-3 px-3.5">
                                            <Badge
                                                variant={
                                                    c.status === 'pending'
                                                        ? 'warning'
                                                        : c.status === 'approved'
                                                            ? 'success'
                                                            : 'secondary'
                                                }
                                                className="capitalize"
                                            >
                                                {c.status}
                                            </Badge>
                                        </td>
                                        <td className="py-3 px-3.5 text-xs text-muted-foreground whitespace-nowrap">
                                            {formatDate(c.submitted_at)}
                                        </td>
                                        <td className="py-3 px-3.5">
                                            <div className="flex items-center gap-1">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => setSelected(c)}
                                                    title="View details"
                                                >
                                                    <Eye size={14} />
                                                </Button>
                                                {c.conflicting_rule_id && (
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setComparing(c)}
                                                        title="Compare rules side by side"
                                                    >
                                                        <GitCompare size={14} />
                                                    </Button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Detail Modal */}
            {selected && (
                <ConflictDetailModal
                    conflict={selected}
                    onClose={() => setSelected(null)}
                    onDismiss={(id) => dismissMutation.mutate(id)}
                    dismissing={dismissMutation.isPending}
                    onCompare={(c) => {
                        setSelected(null);
                        setComparing(c);
                    }}
                    onResolve={(c) => {
                        setSelected(null);
                        setResolving(c);
                    }}
                    onDelete={(id) => deleteMutation.mutate(id)}
                    deleting={deleteMutation.isPending}
                />
            )}

            {/* Edit & Resolve Modal */}
            {resolving && (
                <ResolveEditorModal
                    conflict={resolving}
                    onClose={() => setResolving(null)}
                    onResolved={() => {
                        queryClient.invalidateQueries({ queryKey: ['conflicts'] });
                    }}
                />
            )}

            {/* Side-by-Side Compare Modal */}
            {comparing && (
                <RuleCompareModal
                    conflict={comparing}
                    onClose={() => setComparing(null)}
                />
            )}
        </div>
    );
}
