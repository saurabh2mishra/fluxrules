import React from 'react';
import type { ConditionDSL, ConditionGroup, ConditionLeaf } from '../../types/rule';
import { Button } from '../ui/button';
import { Plus, PlusCircle, Trash2, GitBranch } from 'lucide-react';

const OPS = ['==', '!=', '>', '>=', '<', '<=', 'in', 'contains'];

/* UI-only: Depth-based accent colors for visual nesting distinction */
const DEPTH_ACCENTS = [
    { border: 'border-l-primary/30', bg: 'bg-primary/[0.03]', pill: 'bg-primary/10 text-primary' },
    { border: 'border-l-violet-500/30', bg: 'bg-violet-500/[0.03]', pill: 'bg-violet-500/10 text-violet-600 dark:text-violet-400' },
    { border: 'border-l-teal-500/30', bg: 'bg-teal-500/[0.03]', pill: 'bg-teal-500/10 text-teal-600 dark:text-teal-400' },
    { border: 'border-l-amber-500/30', bg: 'bg-amber-500/[0.03]', pill: 'bg-amber-500/10 text-amber-600 dark:text-amber-400' },
];

interface ConditionBuilderProps {
    value: ConditionGroup;
    onChange: (tree: ConditionGroup) => void;
}

export function ConditionBuilder({ value, onChange }: ConditionBuilderProps) {
    return <GroupNode node={value} onChange={onChange} depth={0} />;
}

function GroupNode({
    node,
    onChange,
    depth,
}: {
    node: ConditionGroup;
    onChange: (n: ConditionGroup) => void;
    depth: number;
}) {
    const updateOp = (op: 'AND' | 'OR') => onChange({ ...node, op });

    const addCondition = () =>
        onChange({ ...node, children: [...node.children, { type: 'condition', field: '', op: '==', value: '' }] });

    const addGroup = () =>
        onChange({ ...node, children: [...node.children, { type: 'group', op: 'AND', children: [] }] });

    const removeChild = (idx: number) =>
        onChange({ ...node, children: node.children.filter((_, i) => i !== idx) });

    const updateChild = (idx: number, child: ConditionDSL) => {
        const children = [...node.children];
        children[idx] = child;
        onChange({ ...node, children });
    };

    /* UI-only: pick accent for nesting depth */
    const accent = DEPTH_ACCENTS[depth % DEPTH_ACCENTS.length];

    return (
        <div
            className={`relative rounded-xl border border-border/50 ${depth > 0 ? `border-l-[3px] ${accent.border}` : ''} ${accent.bg} p-4 transition-all duration-150`}
            style={{ marginLeft: depth > 0 ? '0.75rem' : 0 }}
        >
            {/* Group header: operator pill + action buttons */}
            <div className="flex items-center gap-2 mb-3 flex-wrap">
                {/* Depth icon indicator */}
                {depth > 0 && (
                    <GitBranch size={13} className="text-muted-foreground/40 shrink-0" />
                )}

                {/* Operator pill */}
                <select
                    value={node.op}
                    onChange={(e) => updateOp(e.target.value as 'AND' | 'OR')}
                    className={`h-7 rounded-full px-3 text-xs font-bold uppercase tracking-wider border-0 cursor-pointer transition-colors ${accent.pill}`}
                    aria-label="Logical operator"
                >
                    <option value="AND">AND</option>
                    <option value="OR">OR</option>
                </select>

                <div className="flex items-center gap-1.5 ml-auto">
                    <Button size="sm" variant="ghost" type="button" onClick={addCondition} className="text-xs gap-1 h-7">
                        <Plus size={12} /> Condition
                    </Button>
                    <Button size="sm" variant="ghost" type="button" onClick={addGroup} className="text-xs gap-1 h-7">
                        <PlusCircle size={12} /> Group
                    </Button>
                </div>
            </div>

            {/* Children */}
            <div className="space-y-2">
                {node.children.length === 0 && (
                    <p className="text-xs text-muted-foreground/50 text-center py-3 italic">
                        No conditions yet — add a condition or group above.
                    </p>
                )}
                {node.children.map((child, idx) => (
                    <div key={idx} className="flex items-start gap-1.5 group/row">
                        <div className="flex-1 min-w-0">
                            {child.type === 'group' ? (
                                <GroupNode
                                    node={child as ConditionGroup}
                                    onChange={(updated) => updateChild(idx, updated)}
                                    depth={depth + 1}
                                />
                            ) : (
                                <LeafNode
                                    node={child as ConditionLeaf}
                                    onChange={(updated) => updateChild(idx, updated)}
                                />
                            )}
                        </div>
                        <Button
                            size="sm"
                            variant="ghost"
                            type="button"
                            className="mt-1 h-7 w-7 p-0 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
                            onClick={() => removeChild(idx)}
                            aria-label="Remove"
                        >
                            <Trash2 size={13} />
                        </Button>
                    </div>
                ))}
            </div>
        </div>
    );
}

function LeafNode({ node, onChange }: { node: ConditionLeaf; onChange: (n: ConditionLeaf) => void }) {
    const handleValue = (raw: string) => {
        try {
            onChange({ ...node, value: JSON.parse(raw) });
        } catch {
            onChange({ ...node, value: raw });
        }
    };

    return (
        <div className="condition-item">
            <input
                type="text"
                placeholder="field_name"
                value={node.field}
                onChange={(e) => onChange({ ...node, field: e.target.value })}
                className="w-32 font-medium"
                aria-label="Field name"
            />
            <select
                value={node.op}
                onChange={(e) => onChange({ ...node, op: e.target.value })}
                aria-label="Operator"
            >
                {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <input
                type="text"
                placeholder="value"
                value={typeof node.value === 'string' ? node.value : JSON.stringify(node.value)}
                onChange={(e) => handleValue(e.target.value)}
                className="w-32"
                aria-label="Value"
            />
        </div>
    );
}
