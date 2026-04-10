import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Edit, Trash2, Copy, Clock, Eye } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { VersionHistoryModal } from './VersionHistoryModal';
import { rulesApi } from '../../api/rules';
import type { Rule } from '../../types/rule';
import { toast } from 'sonner';
import { formatDate } from '../../lib/utils';
import {
    AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader,
    AlertDialogTitle, AlertDialogDescription, AlertDialogFooter,
    AlertDialogAction, AlertDialogCancel,
} from '../ui/alert-dialog';

interface RuleCardProps {
    rule: Rule;
    onDeleted: () => void;
}

/* Helper: format condition DSL to readable string */
function formatCondition(dsl: any): string {
    if (!dsl) return 'No conditions';

    if (dsl.type === 'condition') {
        const value = typeof dsl.value === 'string' ? `"${dsl.value}"` : dsl.value;
        return `${dsl.field} ${dsl.op} ${value}`;
    }

    if (dsl.type === 'group') {
        const children = dsl.children?.map(formatCondition).join(` ${dsl.op} `) || '';
        return children ? children : 'Empty group';
    }

    return 'Unknown condition';
}

/* UI-only: modernized RuleCard — cleaner layout, softer borders, improved spacing */
export function RuleCard({ rule, onDeleted }: RuleCardProps) {
    const [showVersions, setShowVersions] = useState(false);
    const [showDetails, setShowDetails] = useState(false);
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
                        <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                            <span className="text-foreground/70">Description:</span> {rule.description}
                        </p>
                    )}
                </div>

                {/* Actions - show more on hover for clean look */}
                <div className="flex items-center gap-1 flex-shrink-0 flex-wrap justify-end">
                    <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={() => navigate(`/rules/${rule.id}/edit`)}
                        title="Edit rule"
                    >
                        <Edit size={13} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowDetails(true)} title="Show Details">
                        <Eye size={13} />
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

            {/* Condition and Action preview */}
            <div className="px-5 pb-5">
                <div className="space-y-1 text-xs text-muted-foreground">
                    <div>Conditions: {formatCondition(rule.condition_dsl)}</div>
                    <div>Action: {rule.action}</div>
                </div>
            </div>

            {/* Rule Details Dialog */}
            <Dialog open={showDetails} onOpenChange={(o) => !o && setShowDetails(false)}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Eye size={16} />
                            Rule: {rule.name}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div><span className="text-muted-foreground text-xs">ID:</span> {rule.id}</div>
                            <div><span className="text-muted-foreground text-xs">Version:</span> v{rule.current_version}</div>
                            <div><span className="text-muted-foreground text-xs">Group:</span> {rule.group || '—'}</div>
                            <div><span className="text-muted-foreground text-xs">Priority:</span> {rule.priority}</div>
                            <div><span className="text-muted-foreground text-xs">Enabled:</span> <Badge variant={rule.enabled ? 'success' : 'secondary'}>{rule.enabled ? 'Yes' : 'No'}</Badge></div>
                            <div><span className="text-muted-foreground text-xs">Action:</span> {rule.action}</div>
                            <div><span className="text-muted-foreground text-xs">Created:</span> {formatDate(rule.created_at)}</div>
                            {rule.updated_at !== rule.created_at && (
                                <div><span className="text-muted-foreground text-xs">Updated:</span> {formatDate(rule.updated_at)}</div>
                            )}
                        </div>

                        {rule.description && (
                            <div>
                                <div className="text-muted-foreground text-xs mb-1">Description</div>
                                <p className="text-sm">{rule.description}</p>
                            </div>
                        )}

                        <div>
                            <div className="text-muted-foreground text-xs mb-1">Condition DSL</div>
                            <pre className="json-pre text-xs">
                                {JSON.stringify(rule.condition_dsl, null, 2)}
                            </pre>
                        </div>
                    </div>
                    <div className="flex justify-end mt-4">
                        <Button variant="ghost" onClick={() => setShowDetails(false)}>Close</Button>
                    </div>
                </DialogContent>
            </Dialog>

            <VersionHistoryModal
                ruleId={rule.id}
                open={showVersions}
                onClose={() => setShowVersions(false)}
            />
        </div>
    );
}
