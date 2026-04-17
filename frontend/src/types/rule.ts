export interface ConditionLeaf {
    type: 'condition';
    field: string;
    op: string;
    value: unknown;
}

export interface ConditionGroup {
    type: 'group';
    op: 'AND' | 'OR';
    children: Array<ConditionGroup | ConditionLeaf>;
}

export type ConditionDSL = ConditionGroup | ConditionLeaf;

export interface Rule {
    id: number;
    name: string;
    description?: string | null;
    group?: string | null;
    priority: number;
    enabled: boolean;
    condition_dsl: ConditionDSL;
    action: string;
    created_at: string;
    updated_at: string;
    current_version: number;
}

export interface RuleCreate {
    name: string;
    description?: string | null;
    group?: string | null;
    priority?: number;
    enabled?: boolean;
    condition_dsl: ConditionDSL;
    action: string;
    evaluation_mode?: 'stateless' | 'stateful';
    rule_metadata?: Record<string, unknown>;
}

export type RuleUpdate = Partial<RuleCreate>;

export interface RuleVersion {
    version: number;
    created_at: string;
    rule_id: number;
    snapshot?: Record<string, unknown>;
}

export interface RuleVersionDiff {
    rule_id: number;
    version1: number;
    version2: number;
    differences: Record<string, { version1: unknown; version2: unknown }>;
}

export interface MatchedRule {
    id: number;
    name: string;
    action: string;
    priority: number;
    group?: string | null;
}

export interface SimulateResponse {
    matched_rules: MatchedRule[];
    explanations?: Record<string, string>;
    stats?: {
        total_rules: number;
        candidates_evaluated: number;
        evaluation_time_ms: number;
        optimization: string;
    };
}

export interface AvailableAction {
    name: string;
    description: string;
    category?: string;
}

export interface ValidationConflict {
    type: string;
    description: string;
    existing_rule_id?: number;
    existing_rule_name?: string;
}

export interface ValidationResult {
    conflicts: ValidationConflict[];
    similar_rules: Array<{
        rule_id: number;
        rule_name: string;
        similarity_score: number;
        reasons: string[];
        group?: string;
    }>;
}
