export interface RuntimeSummary {
    coverage_pct: number;
    triggered_rules: number;
    total_rules: number;
    rules_never_fired_count: number;
    events_processed: number;
    rules_fired: number;
    avg_processing_time_ms: number;
}

export interface TopRule {
    id: number;
    name: string;
    hit_count: number;
    avg_exec_time_ms: number;
    last_fired?: string | null;
}

export interface RuntimeAnalytics {
    summary: RuntimeSummary;
    top_hot_rules?: TopRule[];
    cold_rules?: TopRule[];
    recent_explanations?: ExplanationItem[];
}

export interface TopRulesResponse {
    top_hot_rules: TopRule[];
    cold_rules: TopRule[];
}

export interface ExplanationItem {
    rule_id: number;
    rule_name: string;
    event_id?: string;
    explanation: string;
    created_at: string;
}

export interface ExplanationsResponse {
    items: ExplanationItem[];
}

export interface GraphSummary {
    total_rules: number;
    filtered_rules: number;
    pair_count: number;
    isolated_rules: ConnectedRule[];
    most_connected_rules: ConnectedRule[];
    top_shared_fields: SharedField[];
    available_groups: string[];
}

export interface ConnectedRule {
    name: string;
    group?: string;
    connections: number;
    field_count: number;
}

export interface SharedField {
    field: string;
    rule_count: number;
    pair_count: number;
}
