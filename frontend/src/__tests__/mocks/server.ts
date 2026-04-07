import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

const API_BASE = '/api/v1';

// Default handlers — override per test as needed
export const handlers = [
    // Auth
    http.post(`${API_BASE}/auth/token`, () =>
        HttpResponse.json({ access_token: 'test-token', token_type: 'bearer' }),
    ),
    http.post(`${API_BASE}/auth/register`, () =>
        HttpResponse.json({ id: 1, username: 'testuser', email: 'test@example.com', role: 'business' }),
    ),

    // Rules
    http.get(`${API_BASE}/rules`, () => HttpResponse.json([])),
    http.get(`${API_BASE}/rules/groups`, () => HttpResponse.json({ groups: [] })),
    http.get(`${API_BASE}/rules/actions/available`, () =>
        HttpResponse.json({ actions: [], categorized: {} }),
    ),
    http.post(`${API_BASE}/rules/simulate`, () =>
        HttpResponse.json({ matched_rules: [], explanations: {} }),
    ),

    // Analytics
    http.get(`${API_BASE}/analytics/runtime`, () =>
        HttpResponse.json({
            summary: {
                coverage_pct: 80,
                triggered_rules: 10,
                total_rules: 20,
                rules_never_fired_count: 10,
                events_processed: 100,
                rules_fired: 50,
                avg_processing_time_ms: 5.2,
            },
        }),
    ),
    http.get(`${API_BASE}/analytics/rules/top`, () =>
        HttpResponse.json({ top_hot_rules: [], cold_rules: [] }),
    ),
    http.get(`${API_BASE}/analytics/explanations`, () =>
        HttpResponse.json({ items: [] }),
    ),

    // Admin
    http.get(`${API_BASE}/admin/schema`, () =>
        HttpResponse.json({ expected_version: '1.0', recorded_version: '1.0', match: true, history: [] }),
    ),
    http.get(`${API_BASE}/admin/db/health`, () =>
        HttpResponse.json({ backend: 'sqlite', url_masked: 'sqlite:///***', is_fallback: false, fallback_enabled: false, environment: 'development' }),
    ),

    // Conflicts
    http.get(`${API_BASE}/rules/conflicts/parked`, () => HttpResponse.json([])),

    // Dependency Graph
    http.get(`${API_BASE}/rules/graph/summary`, () =>
        HttpResponse.json({
            total_rules: 0, filtered_rules: 0, pair_count: 0,
            isolated_rules: [], most_connected_rules: [], top_shared_fields: [], available_groups: [],
        }),
    ),
];

export const server = setupServer(...handlers);
