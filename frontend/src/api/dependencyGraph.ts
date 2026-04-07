import { apiClient } from './client';

export const dependencyGraphApi = {
    summary: (params?: { group?: string; field?: string; rule_name?: string }) =>
        apiClient.get('/rules/graph/summary', { params }),
};
