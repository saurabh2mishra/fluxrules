import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rulesApi } from '../api/rules';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import type { GraphSummary } from '../types/analytics';
import { RefreshCw, Activity } from 'lucide-react';

/* UI-only: refined stat card — rounded-xl, subtle hover */
function StatCard({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
            <div className="text-2xl font-bold text-primary tracking-tight">{value}</div>
            <div className="text-[0.6875rem] text-muted-foreground mt-1.5 font-medium uppercase tracking-wider">{label}</div>
        </div>
    );
}

/* UI-only: refined diagnostic table */
function DiagTable({ rows, cols }: { rows: Record<string, unknown>[]; cols: [string, string][] }) {
    if (!rows || rows.length === 0) return <p className="text-sm text-muted-foreground py-4">No data.</p>;
    return (
        <div className="overflow-x-auto rounded-lg">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border/60">
                        {cols.map(([, label]) => <th key={label} className="text-left py-2.5 px-3 font-semibold text-muted-foreground text-[0.6875rem] uppercase tracking-wider">{label}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={i} className="border-b border-border/30 hover:bg-muted/30 transition-colors">
                            {cols.map(([key]) => (
                                <td key={key} className="py-2.5 px-3">{String(row[key] ?? '—')}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default function DiagnosticsPage() {
    const [groupF, setGroupF] = useState('');
    const [fieldF, setFieldF] = useState('');
    const [ruleF, setRuleF] = useState('');
    const [appliedFilters, setAppliedFilters] = useState<{ group?: string; field?: string; rule_name?: string }>({});

    const { data: summary, isFetching, refetch } = useQuery<GraphSummary>({
        queryKey: ['graph-summary', appliedFilters],
        queryFn: () => rulesApi.graphSummary(appliedFilters).then((r) => r.data),
        staleTime: 30_000,
    });

    const applyFilters = () => {
        setAppliedFilters({
            group: groupF || undefined,
            field: fieldF || undefined,
            rule_name: ruleF || undefined,
        });
    };

    const groups = summary?.available_groups ?? [];

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
                <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-cyan-500/10">
                    <Activity size={18} className="text-cyan-500" />
                </div>
                <h1 className="text-xl font-bold text-foreground">Dependency Diagnostics</h1>
            </div>
            <p className="text-muted-foreground text-sm mb-6 ml-12">
                Insight-first view for shared fields, connected and isolated rules.
            </p>

            {/* Filters — UI-only: wrapped in subtle panel */}
            <div className="flex flex-wrap gap-3 mb-6 items-end p-4 rounded-xl bg-muted/30 border border-border/40">
                <select
                    value={groupF}
                    onChange={(e) => setGroupF(e.target.value)}
                    className="native-select min-w-[140px]"
                    aria-label="Filter by group"
                >
                    <option value="">All Groups</option>
                    {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
                <Input placeholder="Field (e.g. amount)" value={fieldF} onChange={(e) => setFieldF(e.target.value)} className="w-44 bg-card" />
                <Input placeholder="Rule name contains…" value={ruleF} onChange={(e) => setRuleF(e.target.value)} className="w-48 bg-card" />
                <Button onClick={applyFilters}>Apply Filters</Button>
                {isFetching && <RefreshCw size={14} className="animate-spin text-muted-foreground" />}
            </div>

            {summary && (
                <div className="space-y-6">
                    {/* Summary */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <StatCard label="Total Rules" value={summary.total_rules} />
                        <StatCard label="Filtered Rules" value={summary.filtered_rules} />
                        <StatCard label="Rule Pairs (Shared Field)" value={summary.pair_count} />
                        <StatCard label="Isolated Rules" value={summary.isolated_rules?.length ?? 0} />
                    </div>

                    {/* Top Shared Fields */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🏷️</span> Top Shared Fields
                        </h2>
                        <DiagTable
                            rows={summary.top_shared_fields as unknown as Record<string, unknown>[]}
                            cols={[['field', 'Field'], ['rule_count', 'Rules'], ['pair_count', 'Rule Pairs']]}
                        />
                    </div>

                    {/* Most Connected */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🔗</span> Most Connected Rules
                        </h2>
                        <DiagTable
                            rows={summary.most_connected_rules as unknown as Record<string, unknown>[]}
                            cols={[['name', 'Rule'], ['group', 'Group'], ['connections', 'Connections'], ['field_count', 'Fields']]}
                        />
                    </div>

                    {/* Isolated */}
                    <div className="border border-border/50 rounded-xl p-5 bg-card/50">
                        <h2 className="font-semibold mb-4 text-foreground flex items-center gap-2">
                            <span className="text-base">🧊</span> Isolated Rules
                        </h2>
                        <DiagTable
                            rows={summary.isolated_rules as unknown as Record<string, unknown>[]}
                            cols={[['name', 'Rule'], ['group', 'Group'], ['connections', 'Connections'], ['field_count', 'Fields']]}
                        />
                    </div>
                </div>
            )}

            {!summary && !isFetching && (
                <div className="text-center py-16 text-muted-foreground">
                    <Button onClick={() => refetch()}>Load Diagnostics</Button>
                </div>
            )}
        </div>
    );
}
