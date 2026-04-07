import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { rulesApi } from '../../api/rules';
import type { EngineStats } from '../../types/admin';
import { Button } from '../ui/button';
import { Spinner, FullPageSpinner } from '../ui/spinner';
import { Badge } from '../ui/badge';
import { RefreshCw, Zap, Trash2, RotateCcw } from 'lucide-react';

/* UI-only: refined stat card */
function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
    return (
        <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
            <div className={`text-2xl font-bold tracking-tight ${color ?? 'text-foreground'}`}>{value}</div>
            <div className="text-[0.6875rem] text-muted-foreground mt-1.5 font-medium uppercase tracking-wider">{label}</div>
        </div>
    );
}

export function EngineTab() {
    const queryClient = useQueryClient();

    const { data: stats, isLoading, refetch, isFetching } = useQuery<EngineStats>({
        queryKey: ['engine-stats'],
        queryFn: () => rulesApi.engineStats().then((r) => r.data),
        staleTime: 15_000,
    });

    const invalidateMutation = useMutation({
        mutationFn: () => rulesApi.invalidateCache(),
        onSuccess: () => {
            toast.success('Cache invalidated');
            queryClient.invalidateQueries({ queryKey: ['engine-stats'] });
        },
        onError: () => toast.error('Failed to invalidate cache'),
    });

    const reloadMutation = useMutation({
        mutationFn: () => rulesApi.reloadEngine(),
        onSuccess: () => {
            toast.success('Engine reloaded');
            queryClient.invalidateQueries({ queryKey: ['engine-stats'] });
        },
        onError: () => toast.error('Failed to reload engine'),
    });

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Rule Engine</h2>
                <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                    <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
                </Button>
            </div>

            {isLoading ? (
                <FullPageSpinner />
            ) : stats ? (
                <div className="space-y-6">
                    {/* Stats */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <StatCard label="Engine Type" value={stats.engine_type} />
                        <StatCard label="Total Evaluations" value={stats.total_evaluations} />
                        <StatCard label="Rules Matched" value={stats.rules_matched} />
                        <StatCard label="Cache Hits" value={stats.cache_hits} color="text-emerald-500" />
                        <StatCard label="Avg Eval Time" value={`${stats.avg_evaluation_time_ms?.toFixed(2) ?? '—'} ms`} />
                        <StatCard label="RETE Compilations" value={stats.rete_compilations} />
                    </div>

                    {/* Cache hit rate — UI-only: rounded-xl panel */}
                    {stats.total_evaluations > 0 && (
                        <div className="border border-border/50 rounded-xl p-5 bg-card">
                            <div className="flex items-center justify-between mb-3">
                                <span className="text-sm font-medium text-foreground">Cache Hit Rate</span>
                                <Badge variant="success">
                                    {((stats.cache_hits / stats.total_evaluations) * 100).toFixed(1)}%
                                </Badge>
                            </div>
                            <div className="w-full bg-muted/50 rounded-full h-2.5">
                                <div
                                    className="bg-emerald-500 h-2.5 rounded-full transition-all duration-500"
                                    style={{ width: `${(stats.cache_hits / stats.total_evaluations) * 100}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* Actions — UI-only: refined panel */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h3 className="text-sm font-semibold mb-4 text-foreground">Engine Controls</h3>
                        <div className="flex flex-wrap gap-3">
                            <Button
                                variant="outline"
                                onClick={() => invalidateMutation.mutate()}
                                disabled={invalidateMutation.isPending}
                            >
                                {invalidateMutation.isPending ? <Spinner size="sm" className="mr-1" /> : <Trash2 size={14} className="mr-1" />}
                                Invalidate Cache
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => reloadMutation.mutate()}
                                disabled={reloadMutation.isPending}
                            >
                                {reloadMutation.isPending ? <Spinner size="sm" className="mr-1" /> : <RotateCcw size={14} className="mr-1" />}
                                Reload Engine
                            </Button>
                        </div>
                        <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                            Caution: Invalidating the cache forces re-evaluation of all rules on the next request. Reloading the engine re-compiles the RETE network.
                        </p>
                    </div>
                </div>
            ) : (
                <p className="text-sm text-muted-foreground py-10 text-center">No engine stats available.</p>
            )}
        </div>
    );
}
