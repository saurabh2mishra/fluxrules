import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Edit, Trash2, ChevronDown, ChevronUp, Copy, Clock } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { VersionHistoryModal } from './VersionHistoryModal';
import { rulesApi } from '../../api/rules';
import type { Rule } from '../../types/rule';
import { toast } from 'sonner';
import {
    AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader,
    AlertDialogTitle, AlertDialogDescription, AlertDialogFooter,
    AlertDialogAction, AlertDialogCancel,
} from '../ui/alert-dialog';

interface RuleCardProps {
    rule: Rule;
    onDeleted: () => void;
}

/* UI-only: modernized RuleCard — cleaner layout, softer borders, improved spacing */
export function RuleCard({ rule, onDeleted }: RuleCardProps) {
    const [expanded, setExpanded] = useState(false);
    const [showVersions, setShowVersions] = useState(false);
    const queryClient = useQueryClient();
    const navigate = useNavigate();

    const deleteMutation = useMutation({
        mutationFn: () => rulesApi.delete(rule.id),
        onSuccess: () => {
            toast.success('Rule deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['rules'] });
            onDeleted();
        },
        onError: () => toast.error('Failed to delete rule'),
    });

    const toggleMutation = useMutation({
        mutationFn: () => rulesApi.update(rule.id, { enabled: !rule.enabled }),
        onSuccess: () => {
            toast.success(`Rule ${rule.enabled ? 'disabled' : 'enabled'}`);
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        },
        onError: () => toast.error('Failed to update rule'),
    });

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(rule, null, 2))
            .then(() => toast.success('Copied to clipboard'))
            .catch(() => toast.error('Copy failed'));
    };

    const conditionPreview =
        typeof rule.condition_dsl === 'string'
            ? rule.condition_dsl
            : JSON.stringify(rule.condition_dsl, null, 2);

    return (
        <div className="group border border-border/50 rounded-xl bg-card shadow-card hover:shadow-card-hover transition-all duration-200">
            {/* Header */}
            <div className="flex items-start justify-between p-5 pb-3 gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2.5 flex-wrap mb-1.5">
                        <h3 className="font-semibold text-[0.9375rem] text-foreground truncate">{rule.name}</h3>
                        <Badge
                            variant={rule.enabled ? 'success' : 'destructive'}
                            className="cursor-pointer text-[0.6875rem]"
                            onClick={() => toggleMutation.mutate()}
                            title="Click to toggle"
                        >
                            {rule.enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                    </div>
                    <div className="flex gap-4 text-xs text-muted-foreground flex-wrap">
                        <span className="inline-flex items-center gap-1">
                            Group: <span className="font-medium text-foreground/70">{rule.group || '—'}</span>
                        </span>
                        <span className="inline-flex items-center gap-1">
                            Priority: <span className="font-medium text-foreground/70">{rule.priority}</span>
                        </span>
                        <span className="text-muted-foreground/60">v{rule.current_version}</span>
                    </div>
                    {rule.description && (
                        <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{rule.description}</p>
                    )}
                </div>

                {/* Actions - show more on hover for clean look */}
                <div className="flex items-center gap-1 flex-shrink-0 flex-wrap justify-end">
                    <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={() => navigate(`/rules/${rule.id}/edit`)}
                    >
                        <Edit size={13} /> Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowVersions(true)} title="Version history">
                        <Clock size={13} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={handleCopy} title="Copy JSON">
                        <Copy size={13} />
                    </Button>
                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button size="sm" variant="ghost" className="text-foreground/50 hover:text-destructive hover:bg-destructive/10" title="Delete rule">
                                <Trash2 size={13} />
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Delete "{rule.name}"?</AlertDialogTitle>
                                <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deleteMutation.mutate()}>Delete</AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </div>
            </div>

            {/* Condition preview (always visible) */}
            <div className="px-5 pb-3">
                <pre className="json-pre max-h-28 text-xs">{conditionPreview}</pre>
            </div>

            {/* Expand/collapse */}
            <div className="px-5 pb-4">
                <button
                    onClick={() => setExpanded((e) => !e)}
                    aria-expanded={expanded}
                    className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                    {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                    {expanded ? 'Hide details' : 'Show details'}
                </button>
            </div>

            {/* Expandable details */}
            {expanded && (
                <div className="px-5 pb-5 border-t border-border/40 pt-4 space-y-3 animate-fade-in">
                    <div>
                        <p className="text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Action</p>
                        <pre className="json-pre text-xs">{rule.action}</pre>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">Full JSON</p>
                        <pre className="json-pre text-xs">{JSON.stringify(rule, null, 2)}</pre>
                    </div>
                </div>
            )}

            <VersionHistoryModal
                ruleId={rule.id}
                open={showVersions}
                onClose={() => setShowVersions(false)}
            />
        </div>
    );
}
