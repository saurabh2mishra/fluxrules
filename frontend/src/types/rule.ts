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

export type PrimitiveValue = string | number | boolean | null;

export interface IntentPredicate {
    field: string;
    op: string;
    value: PrimitiveValue;
}

export interface IntentPattern {
    intent: string;
    where: IntentPredicate[];
}

export type TimeWindowUnit = 'minutes' | 'hours' | 'days';

export interface TimeWindow {
    value: number;
    unit: TimeWindowUnit;
}

export interface AccumulateDSL {
    type: 'accumulate';
    source_event: string;
    metric_field: string;
    metric_op: '>' | '>=' | '<' | '<=' | '==' | '!=';
    threshold: number;
    window: TimeWindow;
    group_by: string[];
}

export interface SequenceDSL {
    type: 'sequence';
    steps: [IntentPattern, IntentPattern];
    within: TimeWindow;
}

export interface CrossFactJoinDSL {
    type: 'cross_fact_join';
    left: IntentPattern;
    right: IntentPattern;
    join_on: Array<{
        left_field: string;
        right_field: string;
    }>;
    match: 'all' | 'any';
}

export type AdvancedConditionDSL = AccumulateDSL | SequenceDSL | CrossFactJoinDSL;

export type ConditionDSL = ConditionGroup | ConditionLeaf | AdvancedConditionDSL;

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
