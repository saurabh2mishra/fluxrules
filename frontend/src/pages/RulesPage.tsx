import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { rulesApi } from '../api/rules';
import { RuleCard } from '../components/rules/RuleCard';
import { RuleFilters } from '../components/rules/RuleFilters';
import { Button } from '../components/ui/button';
import { Search, RefreshCw, List } from 'lucide-react';
import type { Rule } from '../types/rule';

const LIMIT = 50;

export default function RulesPage() {
    const [skip, setSkip] = useState(0);
    const [allRules, setAllRules] = useState<Rule[]>([]);
    const [allLoaded, setAllLoaded] = useState(false);
    const [search, setSearch] = useState('');
    const [groupFilter, setGroupFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const queryClient = useQueryClient();

    const { isFetching, refetch } = useQuery({
        queryKey: ['rules', skip],
        queryFn: async () => {
            const res = await rulesApi.list(skip, LIMIT);
            const rules: Rule[] = res.data;
            if (skip === 0) {
                setAllRules(rules);
            } else {
                setAllRules((prev) => [...prev, ...rules]);
            }
            if (rules.length < LIMIT) setAllLoaded(true);
            return rules;
        },
        staleTime: 30_000,
    });

    const { data: groupData } = useQuery({
        queryKey: ['rule-groups'],
        queryFn: () => rulesApi.groups().then((r) => r.data.groups),
        staleTime: 60_000,
    });

    const filtered = useMemo(() => {
        let list = allRules;
        if (search) {
            const s = search.toLowerCase();
            list = list.filter(
                (r) =>
                    r.name.toLowerCase().includes(s) ||
                    (r.description ?? '').toLowerCase().includes(s)
            );
        }
        if (groupFilter) list = list.filter((r) => r.group === groupFilter);
        if (statusFilter !== '') list = list.filter((r) => String(r.enabled) === statusFilter);
        return list;
    }, [allRules, search, groupFilter, statusFilter]);

    const handleLoadMore = () => {
        setSkip((s) => s + LIMIT);
    };

    const handleRefresh = () => {
        setSkip(0);
        setAllLoaded(false);
        queryClient.invalidateQueries({ queryKey: ['rules'] });
        queryClient.invalidateQueries({ queryKey: ['rule-groups'] });
        refetch();
    };

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10">
                        <List size={18} className="text-primary" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-foreground">Rules</h1>
                        <p className="text-xs text-muted-foreground">
                            {allRules.length > 0 && (
                                <>{filtered.length} of {allRules.length} rules</>
                            )}
                        </p>
                    </div>
                </div>
                <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isFetching}>
                    <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
                    Refresh
                </Button>
            </div>

            {/* Filters */}
            <RuleFilters
                search={search}
                onSearchChange={setSearch}
                groupFilter={groupFilter}
                onGroupFilterChange={setGroupFilter}
                statusFilter={statusFilter}
                onStatusFilterChange={setStatusFilter}
                groups={groupData ?? []}
            />

            {/* Loading */}
            {isFetching && allRules.length === 0 && (
                <div className="flex items-center justify-center py-16 text-muted-foreground">
                    <RefreshCw size={18} className="animate-spin mr-2" /> Loading rules…
                </div>
            )}

            {/* Empty */}
            {!isFetching && filtered.length === 0 && (
                <div className="text-center py-20 text-muted-foreground animate-fade-in">
                    <Search size={44} className="mx-auto mb-4 opacity-20" />
                    <h3 className="font-semibold text-base text-foreground">No Rules Found</h3>
                    <p className="text-sm mt-1">Try adjusting your search or filter criteria.</p>
                </div>
            )}

            {/* Rules list */}
            <div className="space-y-3">
                {filtered.map((rule) => (
                    <RuleCard
                        key={rule.id}
                        rule={rule}
                        onDeleted={() => {
                            setAllRules((prev) => prev.filter((r) => r.id !== rule.id));
                        }}
                    />
                ))}
            </div>

            {/* Load more */}
            {!allLoaded && allRules.length > 0 && (
                <div className="flex justify-center mt-8">
                    <Button variant="outline" onClick={handleLoadMore} disabled={isFetching}>
                        {isFetching ? <RefreshCw size={14} className="animate-spin mr-1" /> : null}
                        Load More
                    </Button>
                </div>
            )}
        </div>
    );
}
