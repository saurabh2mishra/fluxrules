import { apiClient } from './client';

export const analyticsApi = {
    runtime: () => apiClient.get('/analytics/runtime'),
    topRules: (limit = 10) => apiClient.get('/analytics/rules/top', { params: { limit } }),
    explanations: (limit = 20) => apiClient.get('/analytics/explanations', { params: { limit } }),
};
