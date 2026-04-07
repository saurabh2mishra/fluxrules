import { apiClient } from './client';
import type { AuditPolicyCreate } from '../types/admin';

export const adminApi = {
    schema: () => apiClient.get('/admin/schema'),
    dbHealth: () => apiClient.get('/admin/db/health'),
    auditIntegrity: (limit = 200) => apiClient.get('/admin/audit/integrity', { params: { limit } }),
    auditRetention: () => apiClient.post('/admin/audit/retention', {}),
    listPolicies: () => apiClient.get('/admin/audit-policy'),
    createPolicy: (body: AuditPolicyCreate) => apiClient.post('/admin/audit-policy', body),
    updatePolicy: (id: number, body: Partial<AuditPolicyCreate>) =>
        apiClient.patch(`/admin/audit-policy/${id}`, body),
    deletePolicy: (id: number) => apiClient.delete(`/admin/audit-policy/${id}`),
    listReports: (limit = 50) => apiClient.get('/admin/audit-report', { params: { limit } }),
    getReport: (id: number) => apiClient.get(`/admin/audit-report/${id}`),
    runAudit: (scope: string) => apiClient.post('/admin/audit-run', { scope }),
};
