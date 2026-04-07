export interface ConflictedRule {
    id: number;
    name: string;
    description?: string | null;
    group?: string | null;
    priority: number;
    enabled: boolean;
    condition_dsl: unknown;
    action: string;
    conflict_type: string;
    conflict_description: string;
    conflicting_rule_id?: number | null;
    conflicting_rule_name?: string | null;
    status: 'pending' | 'approved' | 'dismissed';
    submitted_at: string;
    reviewed_at?: string | null;
    review_notes?: string | null;
}

export type ConflictStatus = 'pending' | 'approved' | 'dismissed' | '';

export interface ConflictTypeConfig {
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
    description: string;
}

export const CONFLICT_TYPE_CONFIG: Record<string, ConflictTypeConfig> = {
    brms_overlap: {
        label: '🔀 Condition Overlap',
        color: '#e67e22',
        bgColor: 'rgba(230, 126, 34, 0.08)',
        borderColor: '#e67e22',
        description: 'These rules have overlapping conditions and may fire on the same input.',
    },
    duplicate_condition: {
        label: '📋 Duplicate Condition',
        color: '#e74c3c',
        bgColor: 'rgba(231, 76, 60, 0.08)',
        borderColor: '#e74c3c',
        description: 'This rule has the same condition and action as an existing rule.',
    },
    priority_collision: {
        label: '⚡ Priority Collision',
        color: '#f59e0b',
        bgColor: 'rgba(245, 158, 11, 0.08)',
        borderColor: '#f59e0b',
        description: 'Multiple rules share the same priority in the same group.',
    },
    brms_dead_rule: {
        label: '💀 Dead Rule',
        color: '#6b7280',
        bgColor: 'rgba(107, 114, 128, 0.08)',
        borderColor: '#6b7280',
        description: 'This rule has contradictory conditions and can never fire.',
    },
    duplicate_name: {
        label: '🏷️ Duplicate Name',
        color: '#8b5cf6',
        bgColor: 'rgba(139, 92, 246, 0.08)',
        borderColor: '#8b5cf6',
        description: 'A rule with this name already exists.',
    },
};

export function getConflictTypeConfig(type: string): ConflictTypeConfig {
    return CONFLICT_TYPE_CONFIG[type] ?? {
        label: `⚠️ ${type || 'Unknown'}`,
        color: '#6b7280',
        bgColor: 'rgba(107, 114, 128, 0.08)',
        borderColor: '#6b7280',
        description: '',
    };
}
