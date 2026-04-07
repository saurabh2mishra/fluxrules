import { apiClient } from './client';
import type {
    Rule, RuleCreate, RuleUpdate, RuleVersion, RuleVersionDiff,
    SimulateResponse, ValidationResult,
} from '../types/rule';

export const rulesApi = {
    list: (skip = 0, limit = 50) =>
        apiClient.get<Rule[]>('/rules', { params: { skip, limit } }),

    groups: () =>
        apiClient.get<{ groups: string[] }>('/rules/groups'),

    get: (id: number) =>
        apiClient.get<Rule>(`/rules/${id}`),

    create: (body: RuleCreate) =>
        apiClient.post<Rule>('/rules', body),

    update: (id: number, body: RuleUpdate) =>
        apiClient.put<Rule>(`/rules/${id}`, body),

    patch: (id: number, body: Partial<Rule>) =>
        apiClient.patch<Rule>(`/rules/${id}`, body),

    delete: (id: number) =>
        apiClient.delete(`/rules/${id}`),

    versions: (id: number) =>
        apiClient.get<RuleVersion[]>(`/rules/${id}/versions`),

    versionDiff: (id: number, v1: number, v2: number) =>
        apiClient.get<RuleVersionDiff>(`/rules/${id}/diff/${v1}/${v2}`),

    simulate: (event: Record<string, unknown>) =>
        apiClient.post<SimulateResponse>('/rules/simulate', { event }),

    validate: (body: RuleCreate, ruleId?: number) =>
        apiClient.post<ValidationResult>(
            ruleId ? `/rules/validate?rule_id=${ruleId}` : '/rules/validate',
            body
        ),

    availableActions: () =>
        apiClient.get<{ actions: Array<{ name: string; description: string; category?: string }>; categorized: Record<string, Array<{ name: string; description: string }>> }>('/rules/actions/available'),

    graphSummary: (params?: { group?: string; field?: string; rule_name?: string }) =>
        apiClient.get('/rules/graph/summary', { params }),

    parkedConflicts: (status?: string) =>
        apiClient.get('/rules/conflicts/parked', { params: status ? { status } : {} }),

    resolveConflict: (id: number, body: RuleCreate) =>
        apiClient.post(`/rules/conflicts/parked/${id}/resolve`, body),

    dismissConflict: (id: number, notes?: string) =>
        apiClient.put(`/rules/conflicts/parked/${id}`, null, {
            params: { action: 'dismiss', ...(notes ? { notes } : {}) },
        }),

    deleteConflict: (id: number) =>
        apiClient.delete(`/rules/conflicts/parked/${id}`),

    bulkImport: (rules: RuleCreate[], validateConflicts = true) =>
        apiClient.post(`/rules/bulk?validate_conflicts=${validateConflicts}`, rules),

    bulkUpload: (file: File, validateConflicts = true) => {
        const fd = new FormData();
        fd.append('file', file);
        return apiClient.post(`/rules/bulk/upload?validate_conflicts=${validateConflicts}`, fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    engineStats: () =>
        apiClient.get('/rules/engine/stats'),

    invalidateCache: () =>
        apiClient.post('/rules/engine/invalidate-cache', {}),

    reloadEngine: () =>
        apiClient.post('/rules/reload', {}),
};
