import { apiClient } from './client';
import type { RuleCreate } from '../types/rule';

export const conflictsApi = {
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
};
