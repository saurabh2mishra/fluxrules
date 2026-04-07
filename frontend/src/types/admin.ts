export interface SchemaInfo {
    expected_version: string;
    recorded_version: string | null;
    match: boolean;
    history: Array<{ version: string; applied_at: string; description?: string }>;
}

export interface DbHealth {
    backend: string;
    url_masked: string;
    is_fallback: boolean;
    fallback_enabled: boolean;
    environment: string;
}

export interface AuditIntegrity {
    total_checked: number;
    valid: number;
    invalid: number;
    unprotected: number;
}

export interface AuditPolicy {
    id: number;
    name: string;
    description?: string | null;
    cron_expression: string;
    scope: string;
    enabled: boolean;
    last_run_at?: string | null;
    next_run_at?: string | null;
    created_by?: number;
}

export interface AuditPolicyCreate {
    name: string;
    description?: string | null;
    cron_expression: string;
    scope: string;
    enabled: boolean;
}

export interface AuditReport {
    id: number;
    status: string;
    scope: string;
    summary?: string;
    integrity_violations: number;
    coverage_pct: number;
    duration_seconds: number;
    rules_checked: number;
    triggered_by: string;
    executed_at?: string | null;
    details_json?: string;
}

export interface EngineStats {
    engine_type: string;
    total_evaluations: number;
    rules_matched: number;
    cache_hits: number;
    avg_evaluation_time_ms: number;
    rete_compilations: number;
}
