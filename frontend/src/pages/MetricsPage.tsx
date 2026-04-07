import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '../api/analytics';
import { Button } from '../components/ui/button';
import { RefreshCw, BarChart3 } from 'lucide-react';
import { formatDate } from '../lib/utils';
import type { RuntimeAnalytics, TopRulesResponse, ExplanationsResponse, TopRule, ExplanationItem } from '../types/analytics';

/* UI-only: refined stat card — rounded-xl, softer styling */
function StatCard({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
            <div className="text-2xl font-bold text-primary tracking-tight">{value}</div>
            <div className="text-[0.6875rem] text-muted-foreground mt-1.5 font-medium uppercase tracking-wider">{label}</div>
        </div>
    );
}

/* UI-only: refined table with better hover and spacing */
function RuleTable({ items }: { items: TopRule[] }) {
    if (!items?.length) return <p className="text-sm text-muted-foreground py-4">No rules to display.</p>;
    return (
        <div className="overflow-x-auto rounded-lg">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border/60">
                        {['Rule', 'Hit Count', 'Avg Exec Time', 'Last Fired'].map((h) => (
                            <th key={h} className="text-left py-2.5 px-3 text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {items.map((rule) => (
                        <tr key={rule.id} className="border-b border-border/30 hover:bg-muted/30 transition-colors">
                            <td className="py-2.5 px-3 font-medium text-foreground">{rule.name}</td>
                            <td className="py-2.5 px-3">{rule.hit_count}</td>
                            <td className="py-2.5 px-3">{rule.avg_exec_time_ms?.toFixed(2) ?? '—'} ms</td>
                            <td className="py-2.5 px-3 text-xs text-muted-foreground">{formatDate(rule.last_fired)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default function MetricsPage() {
    const { data: runtime, isFetching: r1, refetch: rf1 } = useQuery<RuntimeAnalytics>({
        queryKey: ['analytics-runtime'],
        queryFn: () => analyticsApi.runtime().then((r) => r.data),
        staleTime: 30_000,
    });

    const { data: topRules, isFetching: r2 } = useQuery<TopRulesResponse>({
        queryKey: ['analytics-top-rules'],
        queryFn: () => analyticsApi.topRules(10).then((r) => r.data),
        staleTime: 30_000,
    });

    const { data: explanations, isFetching: r3 } = useQuery<ExplanationsResponse>({
        queryKey: ['analytics-explanations'],
        queryFn: () => analyticsApi.explanations(20).then((r) => r.data),
        staleTime: 30_000,
    });

    const isLoading = r1 || r2 || r3;
    const summary = runtime?.summary;

    const handleRefresh = () => {
        rf1();
    };

    return (
        <div className="animate-fade-in">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-amber-500/10">
                        <BarChart3 size={18} className="text-amber-500" />
                    </div>
                    <h1 className="text-xl font-bold text-foreground">Metrics</h1>
                </div>
                <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
                    <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                    Refresh
                </Button>
            </div>

            {isLoading && !summary && (
                <div className="text-center py-16 text-muted-foreground">
                    <RefreshCw size={18} className="animate-spin mx-auto mb-2" /> Loading analytics…
                </div>
            )}

            {summary && (
                <div className="space-y-6">
                    {/* Summary cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <StatCard label="Coverage" value={`${summary.coverage_pct ?? 0}%`} />
                        <StatCard label="Triggered / Total" value={`${summary.triggered_rules ?? 0} / ${summary.total_rules ?? 0}`} />
                        <StatCard label="Never Fired" value={summary.rules_never_fired_count ?? 0} />
                        <StatCard label="Events Processed" value={summary.events_processed ?? 0} />
                        <StatCard label="Rules Fired" value={summary.rules_fired ?? 0} />
                        <StatCard label="Avg Processing" value={`${summary.avg_processing_time_ms ?? 0} ms`} />
                    </div>

                    {/* Hot rules — UI-only: rounded-xl panel */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🔥</span> Top Fired Rules
                        </h2>
                        <RuleTable items={topRules?.top_hot_rules ?? runtime?.top_hot_rules ?? []} />
                    </div>

                    {/* Cold rules */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🧊</span> Never Fired Rules
                        </h2>
                        <RuleTable items={topRules?.cold_rules ?? runtime?.cold_rules ?? []} />
                    </div>

                    {/* Explanations */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🧠</span> Recent Explanations
                        </h2>
                        {(explanations?.items ?? []).length === 0 ? (
                            <p className="text-sm text-muted-foreground py-3">No recent explanations.</p>
                        ) : (
                            <div className="space-y-2">
                                {(explanations?.items ?? []).map((item: ExplanationItem, i: number) => (
                                    <div key={i} className="border border-border/40 rounded-lg p-3.5 text-sm hover:bg-muted/20 transition-colors">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="font-medium text-foreground">{item.rule_name}</span>
                                            <span className="text-xs text-muted-foreground ml-auto">{formatDate(item.created_at)}</span>
                                        </div>
                                        <code className="text-xs text-muted-foreground font-mono">{item.explanation}</code>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
