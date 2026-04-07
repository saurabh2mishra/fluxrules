import { Input } from '../ui/input';
import { Search } from 'lucide-react';

interface RuleFiltersProps {
    search: string;
    onSearchChange: (value: string) => void;
    groupFilter: string;
    onGroupFilterChange: (value: string) => void;
    statusFilter: string;
    onStatusFilterChange: (value: string) => void;
    groups: string[];
}

/* UI-only: refined filter bar — calmer spacing, styled native selects */
export function RuleFilters({
    search,
    onSearchChange,
    groupFilter,
    onGroupFilterChange,
    statusFilter,
    onStatusFilterChange,
    groups,
}: RuleFiltersProps) {
    return (
        <div className="flex flex-wrap gap-3 mb-6 p-4 rounded-xl bg-muted/30 border border-border/40">
            <div className="relative flex-1 min-w-52">
                <Search size={14} className="absolute left-3 top-2.5 text-muted-foreground/50" />
                <Input
                    placeholder="Search rules…"
                    value={search}
                    onChange={(e) => onSearchChange(e.target.value)}
                    className="pl-9 bg-card"
                />
            </div>
            <select
                value={groupFilter}
                onChange={(e) => onGroupFilterChange(e.target.value)}
                className="native-select min-w-[140px]"
                aria-label="Filter by group"
            >
                <option value="">All Groups</option>
                {groups.map((g) => (
                    <option key={g} value={g}>{g}</option>
                ))}
            </select>
            <select
                value={statusFilter}
                onChange={(e) => onStatusFilterChange(e.target.value)}
                className="native-select min-w-[130px]"
                aria-label="Filter by status"
            >
                <option value="">All Status</option>
                <option value="true">Enabled</option>
                <option value="false">Disabled</option>
            </select>
        </div>
    );
}
