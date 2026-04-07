import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { rulesApi } from '../api/rules';
import { ConditionBuilder } from '../components/rules/ConditionBuilder';
import { VersionHistoryModal } from '../components/rules/VersionHistoryModal';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { JsonEditor } from '../components/ui/json-editor';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import type { ConditionDSL, ConditionGroup, RuleUpdate } from '../types/rule';
import { toast } from 'sonner';
import { Save, Clock, ArrowLeft, Edit } from 'lucide-react';

const DEFAULT_TREE: ConditionGroup = { type: 'group', op: 'AND', children: [] };

/** Ensure the DSL is always a ConditionGroup the visual builder can render.
 *  If the backend returns a bare leaf (type:'condition'), wrap it in an AND group. */
function toGroup(dsl: unknown): ConditionGroup {
    if (dsl && typeof dsl === 'object') {
        const d = dsl as ConditionDSL;
        if (d.type === 'group') return d as ConditionGroup;
        if (d.type === 'condition') return { type: 'group', op: 'AND', children: [d] };
    }
    return DEFAULT_TREE;
}

export default function EditRulePage() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const ruleId = Number(id);

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [group, setGroup] = useState('');
    const [priority, setPriority] = useState(0);
    const [enabled, setEnabled] = useState(true);
    const [action, setAction] = useState('');
    const [conditionTree, setConditionTree] = useState<ConditionGroup>(DEFAULT_TREE);
    const [dslJson, setDslJson] = useState('');
    const [dslError, setDslError] = useState('');
    const [showVersions, setShowVersions] = useState(false);

    const { data: rule, isLoading } = useQuery({
        queryKey: ['rule', ruleId],
        queryFn: () => rulesApi.get(ruleId).then((r) => r.data),
        enabled: !!ruleId,
    });

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

    useEffect(() => {
        if (!rule) return;
        setName(rule.name);
        setDescription(rule.description ?? '');
        setGroup(rule.group ?? '');
        setPriority(rule.priority);
        setEnabled(rule.enabled);
        setAction(rule.action);
        const tree = toGroup(rule.condition_dsl);
        setConditionTree(tree);
        setDslJson(JSON.stringify(tree, null, 2));
    }, [rule]);

    useEffect(() => {
        setDslJson(JSON.stringify(conditionTree, null, 2));
    }, [conditionTree]);

    const handleDslChange = (val: string) => {
        setDslJson(val);
        try {
            const parsed = JSON.parse(val);
            setConditionTree(toGroup(parsed));
            setDslError('');
        } catch {
            setDslError('Invalid JSON');
        }
    };

    const updateMutation = useMutation({
        mutationFn: () => {
            const payload: RuleUpdate = {
                name: name.trim(),
                description: description.trim() || null,
                group: group.trim() || null,
                priority,
                enabled,
                action,
                condition_dsl: conditionTree,
            };
            return rulesApi.update(ruleId, payload);
        },
        onSuccess: () => {
            toast.success('Rule updated successfully!');
            navigate('/rules');
        },
        onError: (err: unknown) => {
            const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
            if (detail && typeof detail === 'object' && 'message' in detail) {
                toast.error((detail as { message: string }).message);
            } else {
                toast.error('Failed to update rule');
            }
        },
    });

    if (isLoading) {
        return <div className="py-16 text-center text-muted-foreground animate-fade-in">Loading rule…</div>;
    }

    if (!rule) {
        return <div className="py-16 text-center text-red-500 animate-fade-in">Rule not found.</div>;
    }

    return (
        <div className="max-w-3xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="flex items-center gap-3 mb-8">
                <Button variant="ghost" size="sm" onClick={() => navigate('/rules')} className="shrink-0">
                    <ArrowLeft size={14} /> Back
                </Button>
                <div className="flex items-center gap-3 flex-1">
                    <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10">
                        <Edit size={16} className="text-primary" />
                    </div>
                    <h1 className="text-xl font-bold text-foreground">Edit Rule</h1>
                </div>
                <Button variant="outline" size="sm" onClick={() => setShowVersions(true)} className="shrink-0">
                    <Clock size={14} /> Versions
                </Button>
            </div>

            <div className="space-y-5">
                {/* Basic Info — UI-only: wrapped in modern card panel */}
                <div className="border border-border/50 rounded-xl p-6 bg-card/50 space-y-4">
                    <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Basic Info</h2>
                    <div>
                        <label className="text-sm font-medium text-foreground">Name *</label>
                        <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-foreground">Description</label>
                        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1.5" rows={2} />
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <label className="text-sm font-medium text-foreground">Group</label>
                            <select
                                value={group}
                                onChange={(e) => setGroup(e.target.value)}
                                className="native-select mt-1.5 w-full"
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

                {/* Conditions — UI-only: refined panel */}
                <div className="border border-border/50 rounded-xl p-6 bg-card/50">
                    <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-4">Conditions</h2>
                    <Tabs defaultValue="visual">
                        <TabsList>
                            <TabsTrigger value="visual">Visual Builder</TabsTrigger>
                            <TabsTrigger value="json">JSON Editor</TabsTrigger>
                        </TabsList>
                        <TabsContent value="visual" className="mt-4">
                            <ConditionBuilder value={conditionTree} onChange={setConditionTree} />
                        </TabsContent>
                        <TabsContent value="json" className="mt-4">
                            <JsonEditor
                                value={dslJson}
                                onChange={handleDslChange}
                                height="250px"
                            />
                            {dslError && <p className="text-xs text-red-500 mt-1.5">{dslError}</p>}
                        </TabsContent>
                    </Tabs>
                </div>

                {/* Action */}
                <div className="border border-border/50 rounded-xl p-6 bg-card/50">
                    <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-4">Action</h2>
                    <div className="space-y-3">
                        <div>
                            <label className="text-sm font-medium text-foreground">Select Action *</label>
                            <select
                                value={action}
                                onChange={(e) => setAction(e.target.value)}
                                className="native-select mt-1.5 w-full"
                            >
                                <option value="">— Select an action —</option>
                                {Object.entries(categorized).map(([cat, actions]) => (
                                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                                        {(actions as Array<{ name: string }>).map((a) => (
                                            <option key={a.name} value={a.name}>{a.name}</option>
                                        ))}
                                    </optgroup>
                                ))}
                                {/* If the saved action isn't in the list, show it as a custom option */}
                                {action && !actionsData?.actions.find((a) => a.name === action) && (
                                    <option value={action}>{action} (saved)</option>
                                )}
                            </select>
                            {selectedActionDesc && (
                                <p className="text-xs text-muted-foreground mt-1.5">{selectedActionDesc}</p>
                            )}
                        </div>
                        <div>
                            <label className="text-sm font-medium text-foreground">
                                Action / Parameters (JSON, optional)
                            </label>
                            <p className="text-xs text-muted-foreground mb-1.5">
                                Leave blank to use the selected action as-is, or paste a JSON override.
                            </p>
                            <JsonEditor
                                value={action}
                                onChange={(val) => setAction(val)}
                                height="100px"
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 mt-8 pt-5 border-t border-border/40">
                <Button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>
                    <Save size={14} /> {updateMutation.isPending ? 'Saving…' : 'Update Rule'}
                </Button>
                <Button variant="outline" onClick={() => navigate('/rules')}>Cancel</Button>
            </div>

            <VersionHistoryModal ruleId={ruleId} open={showVersions} onClose={() => setShowVersions(false)} />
        </div>
    );
}
