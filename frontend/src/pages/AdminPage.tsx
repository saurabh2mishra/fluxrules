import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { adminApi } from '../api/admin';
import { useAuthStore } from '../store/authStore';
import type { AuditPolicy, AuditPolicyCreate, AuditReport } from '../types/admin';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Spinner, FullPageSpinner } from '../components/ui/spinner';
import { EmptyState } from '../components/ui/empty-state';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { BulkImportTab } from '../components/admin/BulkImportTab';
import { EngineTab } from '../components/admin/EngineTab';
import {
    RefreshCw, Shield, Database, ClipboardList, Plus,
    Trash2, Play, CheckCircle, XCircle, Server, Upload, Zap, ShieldOff,
} from 'lucide-react';
import { formatDate } from '../lib/utils';

/* ── Schema Tab ───────────────────────────────────────────────── */
function SchemaTab() {
    const { data, isLoading, refetch, isFetching } = useQuery({
        queryKey: ['admin-schema'],
        queryFn: () => adminApi.schema().then((r) => r.data),
        staleTime: 60_000,
    });

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Schema Version</h2>
                <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                    <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
                </Button>
            </div>
            {isLoading ? <FullPageSpinner /> : data ? (
                <div className="space-y-5">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="border border-border/50 rounded-xl p-5 bg-card">
                            <div className="text-[0.6875rem] text-muted-foreground mb-1.5 uppercase tracking-wider font-medium">Expected Version</div>
                            <div className="font-mono text-sm font-semibold text-foreground">{data.expected_version}</div>
                        </div>
                        <div className="border border-border/50 rounded-xl p-5 bg-card">
                            <div className="text-[0.6875rem] text-muted-foreground mb-1.5 uppercase tracking-wider font-medium">Recorded Version</div>
                            <div className="font-mono text-sm font-semibold text-foreground">{data.recorded_version ?? '—'}</div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {data.match ? (
                            <Badge variant="success"><CheckCircle size={12} className="mr-1" />Versions match</Badge>
                        ) : (
                            <Badge variant="destructive"><XCircle size={12} className="mr-1" />Version mismatch</Badge>
                        )}
                    </div>
                    {data.history?.length > 0 && (
                        <div>
                            <h3 className="text-sm font-semibold mb-3 text-foreground">Migration History</h3>
                            <div className="overflow-x-auto rounded-xl border border-border/50">
                                <table className="w-full text-sm">
                                    <thead className="bg-muted/20">
                                        <tr>
                                            {['Version', 'Applied At', 'Description'].map((h) => (
                                                <th key={h} className="text-left py-2.5 px-3.5 text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.history.map((h: { version: string; applied_at: string; description?: string }) => (
                                            <tr key={h.version} className="border-t border-border/30 hover:bg-muted/20 transition-colors">
                                                <td className="py-2.5 px-3.5 font-mono text-xs">{h.version}</td>
                                                <td className="py-2.5 px-3.5 text-xs text-muted-foreground">{formatDate(h.applied_at)}</td>
                                                <td className="py-2.5 px-3.5 text-xs">{h.description ?? '—'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            ) : null}
        </div>
    );
}

/* ── DB Health Tab ────────────────────────────────────────────── */
function DbHealthTab() {
    const { data, isLoading, refetch, isFetching } = useQuery({
        queryKey: ['admin-db-health'],
        queryFn: () => adminApi.dbHealth().then((r) => r.data),
        staleTime: 30_000,
    });

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Database Health</h2>
                <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                    <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
                </Button>
            </div>
            {isLoading ? <FullPageSpinner /> : data ? (
                <div className="grid grid-cols-2 gap-4">
                    <InfoCard label="Backend" value={data.backend} />
                    <InfoCard label="URL (masked)" value={data.url_masked} mono />
                    <InfoCard label="Environment" value={data.environment} />
                    <InfoCard
                        label="Fallback"
                        value={
                            <Badge variant={data.is_fallback ? 'warning' : 'success'}>
                                {data.is_fallback ? 'Fallback Active' : 'Primary'}
                            </Badge>
                        }
                    />
                    <InfoCard
                        label="Fallback Enabled"
                        value={
                            <Badge variant={data.fallback_enabled ? 'secondary' : 'outline'}>
                                {data.fallback_enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                        }
                    />
                </div>
            ) : null}
        </div>
    );
}

/* UI-only: refined info card */
function InfoCard({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
    return (
        <div className="border border-border/50 rounded-xl p-5 bg-card">
            <div className="text-[0.6875rem] text-muted-foreground mb-1.5 uppercase tracking-wider font-medium">{label}</div>
            <div className={mono ? 'font-mono text-sm break-all text-foreground' : 'text-sm font-medium text-foreground'}>{value}</div>
        </div>
    );
}

/* ── Audit Integrity Tab ──────────────────────────────────────── */
function AuditIntegrityTab() {
    const { data, isLoading, refetch, isFetching } = useQuery({
        queryKey: ['admin-audit-integrity'],
        queryFn: () => adminApi.auditIntegrity().then((r) => r.data),
        staleTime: 30_000,
    });

    const retentionMutation = useMutation({
        mutationFn: () => adminApi.auditRetention(),
        onSuccess: () => { toast.success('Retention policy applied'); refetch(); },
        onError: () => toast.error('Failed to apply retention policy'),
    });

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Audit Integrity</h2>
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => retentionMutation.mutate()}
                        disabled={retentionMutation.isPending}
                    >
                        {retentionMutation.isPending ? <Spinner size="sm" /> : <Play size={13} />}
                        Run Retention
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                        <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
                    </Button>
                </div>
            </div>
            {isLoading ? <FullPageSpinner /> : data ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard label="Total Checked" value={data.total_checked} />
                    <StatCard label="Valid" value={data.valid} color="text-emerald-500" />
                    <StatCard label="Invalid" value={data.invalid} color={data.invalid > 0 ? 'text-red-500' : undefined} />
                    <StatCard label="Unprotected" value={data.unprotected} color={data.unprotected > 0 ? 'text-amber-500' : undefined} />
                </div>
            ) : null}
        </div>
    );
}

/* UI-only: refined stat card */
function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
    return (
        <div className="border border-border/50 rounded-xl p-4 text-center bg-card transition-shadow hover:shadow-card-hover">
            <div className={`text-2xl font-bold tracking-tight ${color ?? 'text-foreground'}`}>{value}</div>
            <div className="text-[0.6875rem] text-muted-foreground mt-1.5 font-medium uppercase tracking-wider">{label}</div>
        </div>
    );
}

/* ── Audit Policies Tab ───────────────────────────────────────── */
function AuditPoliciesTab() {
    const queryClient = useQueryClient();
    const [creating, setCreating] = useState(false);
    const [form, setForm] = useState<AuditPolicyCreate>({
        name: '',
        description: '',
        cron_expression: '0 2 * * *',
        scope: 'all',
        enabled: true,
    });

    const { data: policies, isLoading } = useQuery<AuditPolicy[]>({
        queryKey: ['audit-policies'],
        queryFn: () => adminApi.listPolicies().then((r) => r.data),
        staleTime: 30_000,
    });

    const createMutation = useMutation({
        mutationFn: (body: AuditPolicyCreate) => adminApi.createPolicy(body),
        onSuccess: () => {
            toast.success('Policy created');
            setCreating(false);
            setForm({ name: '', description: '', cron_expression: '0 2 * * *', scope: 'all', enabled: true });
            queryClient.invalidateQueries({ queryKey: ['audit-policies'] });
        },
        onError: () => toast.error('Failed to create policy'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => adminApi.deletePolicy(id),
        onSuccess: () => {
            toast.success('Policy deleted');
            queryClient.invalidateQueries({ queryKey: ['audit-policies'] });
        },
        onError: () => toast.error('Failed to delete policy'),
    });

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
            adminApi.updatePolicy(id, { enabled }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['audit-policies'] }),
        onError: () => toast.error('Failed to update policy'),
    });

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Audit Policies</h2>
                <Button size="sm" onClick={() => setCreating(true)}>
                    <Plus size={14} /> New Policy
                </Button>
            </div>

            {isLoading ? <FullPageSpinner /> : (
                <>
                    {!policies?.length && (
                        <p className="text-sm text-muted-foreground py-10 text-center">No audit policies configured.</p>
                    )}
                    {policies && policies.length > 0 && (
                        <div className="space-y-3">
                            {policies.map((p) => (
                                <div key={p.id} className="border border-border/50 rounded-xl p-5 bg-card flex items-start justify-between gap-3 hover:shadow-card-hover transition-shadow">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="font-medium text-sm text-foreground">{p.name}</span>
                                            <Badge variant={p.enabled ? 'success' : 'secondary'} className="text-xs">
                                                {p.enabled ? 'Enabled' : 'Disabled'}
                                            </Badge>
                                        </div>
                                        {p.description && (
                                            <p className="text-xs text-muted-foreground mb-1.5">{p.description}</p>
                                        )}
                                        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                                            <span>Cron: <code className="font-mono bg-muted/60 px-1.5 py-0.5 rounded-md">{p.cron_expression}</code></span>
                                            <span>Scope: {p.scope}</span>
                                            {p.last_run_at && <span>Last run: {formatDate(p.last_run_at)}</span>}
                                            {p.next_run_at && <span>Next run: {formatDate(p.next_run_at)}</span>}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => toggleMutation.mutate({ id: p.id, enabled: !p.enabled })}
                                            className="text-muted-foreground"
                                        >
                                            {p.enabled ? <XCircle size={14} /> : <CheckCircle size={14} />}
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                                            onClick={() => deleteMutation.mutate(p.id)}
                                        >
                                            <Trash2 size={14} />
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}

            {/* Create Dialog */}
            <Dialog open={creating} onOpenChange={(o) => !o && setCreating(false)}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle>New Audit Policy</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        <div>
                            <Label className="mb-1.5">Name *</Label>
                            <Input
                                value={form.name}
                                onChange={(e) => setForm({ ...form, name: e.target.value })}
                                placeholder="Daily Audit"
                            />
                        </div>
                        <div>
                            <Label className="mb-1.5">Description</Label>
                            <Input
                                value={form.description ?? ''}
                                onChange={(e) => setForm({ ...form, description: e.target.value })}
                                placeholder="Optional description"
                            />
                        </div>
                        <div>
                            <Label className="mb-1.5">Cron Expression *</Label>
                            <Input
                                value={form.cron_expression}
                                onChange={(e) => setForm({ ...form, cron_expression: e.target.value })}
                                placeholder="0 2 * * *"
                                className="font-mono"
                            />
                        </div>
                        <div>
                            <Label className="mb-1.5">Scope</Label>
                            <Input
                                value={form.scope}
                                onChange={(e) => setForm({ ...form, scope: e.target.value })}
                                placeholder="all"
                            />
                        </div>
                        <div className="flex items-center gap-2.5">
                            <input
                                type="checkbox"
                                id="enabled"
                                checked={form.enabled}
                                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                                className="h-4 w-4 rounded"
                            />
                            <label htmlFor="enabled" className="text-sm text-foreground">Enabled</label>
                        </div>
                    </div>
                    <div className="flex justify-end gap-2 mt-4">
                        <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
                        <Button
                            onClick={() => createMutation.mutate(form)}
                            disabled={!form.name || createMutation.isPending}
                        >
                            {createMutation.isPending ? <Spinner size="sm" className="mr-1" /> : null}
                            Create
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}

/* ── Audit Reports Tab ────────────────────────────────────────── */
function AuditReportsTab() {
    const [selectedReport, setSelectedReport] = useState<AuditReport | null>(null);
    const [loadingReport, setLoadingReport] = useState(false);
    const [running, setRunning] = useState(false);
    const [scope, setScope] = useState('all');
    const queryClient = useQueryClient();

    const { data: reports, isLoading, refetch, isFetching } = useQuery<AuditReport[]>({
        queryKey: ['audit-reports'],
        queryFn: () => adminApi.listReports().then((r) => r.data),
        staleTime: 30_000,
    });

    const runMutation = useMutation({
        mutationFn: (s: string) => adminApi.runAudit(s),
        onSuccess: () => {
            toast.success('Audit run started');
            setRunning(false);
            queryClient.invalidateQueries({ queryKey: ['audit-reports'] });
        },
        onError: () => toast.error('Failed to start audit'),
    });

    const handleRowClick = async (report: AuditReport) => {
        setLoadingReport(true);
        try {
            const res = await adminApi.getReport(report.id);
            setSelectedReport(res.data);
        } catch {
            // Fall back to list data if detail fetch fails
            setSelectedReport(report);
            toast.error('Failed to load full report details');
        } finally {
            setLoadingReport(false);
        }
    };

    return (
        <div>
            <div className="flex items-center justify-between mb-5">
                <h2 className="font-semibold text-foreground">Audit Reports</h2>
                <div className="flex gap-2">
                    <Button size="sm" onClick={() => setRunning(true)}>
                        <Play size={13} /> Run Audit
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                        <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
                    </Button>
                </div>
            </div>

            {isLoading ? <FullPageSpinner /> : (
                <>
                    {!reports?.length && (
                        <p className="text-sm text-muted-foreground py-10 text-center">No audit reports available.</p>
                    )}
                    {reports && reports.length > 0 && (
                        <div className="overflow-x-auto rounded-xl border border-border/50">
                            <table className="w-full text-sm">
                                <thead className="bg-muted/20">
                                    <tr>
                                        {['Report ID', 'Scope', 'Status', 'Rules', 'Violations', 'Coverage', 'Duration', 'Executed'].map((h) => (
                                            <th key={h} className="text-left py-3 px-3.5 text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {reports.map((r) => (
                                        <tr
                                            key={r.id}
                                            className="border-t border-border/30 hover:bg-muted/20 cursor-pointer transition-colors"
                                            onClick={() => handleRowClick(r)}
                                        >
                                            <td className="py-3 px-3.5 font-mono text-xs max-w-[100px] truncate">{r.id}</td>
                                            <td className="py-3 px-3.5">{r.scope}</td>
                                            <td className="py-3 px-3.5">
                                                <Badge variant={r.status === 'completed' ? 'success' : r.status === 'failed' ? 'destructive' : 'warning'} className="capitalize">
                                                    {r.status}
                                                </Badge>
                                            </td>
                                            <td className="py-3 px-3.5">{r.rules_checked}</td>
                                            <td className="py-3 px-3.5">
                                                <span className={r.integrity_violations > 0 ? 'text-red-500 font-semibold' : ''}>
                                                    {r.integrity_violations}
                                                </span>
                                            </td>
                                            <td className="py-3 px-3.5">{r.coverage_pct?.toFixed(1) ?? '—'}%</td>
                                            <td className="py-3 px-3.5">{r.duration_seconds?.toFixed(2)}s</td>
                                            <td className="py-3 px-3.5 text-xs text-muted-foreground whitespace-nowrap">
                                                {r.executed_at ? formatDate(r.executed_at) : '—'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}

            {/* Loading overlay for report detail fetch */}
            {loadingReport && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-sm">
                    <Spinner size="lg" />
                </div>
            )}

            {/* Report Detail Dialog — always rendered, controlled via open prop */}
            <Dialog open={!!selectedReport && !loadingReport} onOpenChange={(o) => !o && setSelectedReport(null)}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Report: {String(selectedReport?.id ?? '')}…</DialogTitle>
                    </DialogHeader>
                    {selectedReport && (
                        <div className="space-y-4 mt-2 text-sm">
                            <div className="grid grid-cols-2 gap-4">
                                <div><span className="text-muted-foreground text-xs">Scope:</span> {selectedReport.scope}</div>
                                <div><span className="text-muted-foreground text-xs">Status:</span> <Badge variant={selectedReport.status === 'completed' ? 'success' : 'destructive'} className="capitalize">{selectedReport.status}</Badge></div>
                                <div><span className="text-muted-foreground text-xs">Rules Checked:</span> {selectedReport.rules_checked}</div>
                                <div><span className="text-muted-foreground text-xs">Violations:</span> {selectedReport.integrity_violations}</div>
                                <div><span className="text-muted-foreground text-xs">Coverage:</span> {selectedReport.coverage_pct?.toFixed(2)}%</div>
                                <div><span className="text-muted-foreground text-xs">Duration:</span> {selectedReport.duration_seconds?.toFixed(3)}s</div>
                                <div><span className="text-muted-foreground text-xs">Triggered By:</span> {selectedReport.triggered_by}</div>
                                {selectedReport.executed_at && <div><span className="text-muted-foreground text-xs">Executed:</span> {formatDate(selectedReport.executed_at)}</div>}
                            </div>
                            {selectedReport.summary && (
                                <div>
                                    <div className="text-muted-foreground text-xs mb-1">Summary</div>
                                    <p className="text-sm leading-relaxed">{selectedReport.summary}</p>
                                </div>
                            )}
                            {selectedReport.details_json && (
                                <div>
                                    <div className="text-muted-foreground text-xs mb-1">Details</div>
                                    {(() => {
                                        try {
                                            const details = JSON.parse(selectedReport.details_json!);
                                            if (Array.isArray(details) && details.length > 0) {
                                                // Assume it's an array of audit results with rule information
                                                return (
                                                    <div className="overflow-x-auto rounded-xl border border-border/50">
                                                        <table className="w-full text-xs">
                                                            <thead className="bg-muted/20">
                                                                <tr>
                                                                    {['Rule ID', 'Rule Name', 'Status', 'Violations', 'Details'].map((h) => (
                                                                        <th key={h} className="text-left py-2 px-3 text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
                                                                    ))}
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {details.map((item: any, index: number) => (
                                                                    <tr key={index} className="border-t border-border/30">
                                                                        <td className="py-2 px-3 font-mono">{item.rule_id ?? item.id ?? '—'}</td>
                                                                        <td className="py-2 px-3">{item.rule_name ?? item.name ?? '—'}</td>
                                                                        <td className="py-2 px-3">
                                                                            <Badge variant={item.status === 'passed' ? 'success' : item.status === 'failed' ? 'destructive' : 'warning'} className="text-xs">
                                                                                {item.status ?? '—'}
                                                                            </Badge>
                                                                        </td>
                                                                        <td className="py-2 px-3">
                                                                            <span className={item.violations > 0 ? 'text-red-500 font-semibold' : ''}>
                                                                                {item.violations ?? 0}
                                                                            </span>
                                                                        </td>
                                                                        <td className="py-2 px-3 text-muted-foreground">
                                                                            {item.details ?? item.message ?? '—'}
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                );
                                            } else {
                                                // Fallback to JSON display
                                                return (
                                                    <pre className="json-pre text-xs">
                                                        {JSON.stringify(details, null, 2)}
                                                    </pre>
                                                );
                                            }
                                        } catch {
                                            return (
                                                <pre className="json-pre text-xs">
                                                    {selectedReport.details_json}
                                                </pre>
                                            );
                                        }
                                    })()}
                                </div>
                            )}
                        </div>
                    )}
                    <div className="flex justify-end mt-4">
                        <Button variant="ghost" onClick={() => setSelectedReport(null)}>Close</Button>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Run Audit Dialog */}
            <Dialog open={running} onOpenChange={(o) => !o && setRunning(false)}>
                <DialogContent className="max-w-sm">
                    <DialogHeader><DialogTitle>Run Audit</DialogTitle></DialogHeader>
                    <div className="space-y-3 mt-2">
                        <div>
                            <Label className="mb-1.5">Scope</Label>
                            <Input value={scope} onChange={(e) => setScope(e.target.value)} placeholder="all" />
                        </div>
                    </div>
                    <div className="flex justify-end gap-2 mt-4">
                        <Button variant="ghost" onClick={() => setRunning(false)}>Cancel</Button>
                        <Button onClick={() => runMutation.mutate(scope)} disabled={runMutation.isPending}>
                            {runMutation.isPending ? <Spinner size="sm" className="mr-1" /> : <Play size={13} />}
                            Run
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}

/* ── Main AdminPage ───────────────────────────────────────────── */
export default function AdminPage() {
    const isAdmin = useAuthStore((s) => s.isAdmin());

    if (!isAdmin) {
        return (
            <EmptyState
                icon={<ShieldOff size={48} />}
                title="403 — Admin Access Required"
                description="You do not have permission to view this page. Please contact an administrator if you believe this is an error."
            />
        );
    }

    return (
        <div className="animate-fade-in">
            <div className="flex items-center gap-3 mb-8">
                <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10">
                    <Shield size={18} className="text-primary" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-foreground">Admin</h1>
                    <p className="text-xs text-muted-foreground">System management and audit controls</p>
                </div>
            </div>

            <Tabs defaultValue="schema">
                <TabsList className="mb-6 flex-wrap">
                    <TabsTrigger value="schema">
                        <Server size={14} className="mr-1.5" />Schema
                    </TabsTrigger>
                    <TabsTrigger value="db">
                        <Database size={14} className="mr-1.5" />DB Health
                    </TabsTrigger>
                    <TabsTrigger value="integrity">
                        <CheckCircle size={14} className="mr-1.5" />Integrity
                    </TabsTrigger>
                    <TabsTrigger value="policies">
                        <ClipboardList size={14} className="mr-1.5" />Policies
                    </TabsTrigger>
                    <TabsTrigger value="reports">
                        <Shield size={14} className="mr-1.5" />Reports
                    </TabsTrigger>
                    <TabsTrigger value="engine">
                        <Zap size={14} className="mr-1.5" />Engine
                    </TabsTrigger>
                    <TabsTrigger value="import">
                        <Upload size={14} className="mr-1.5" />Bulk Import
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="schema"><SchemaTab /></TabsContent>
                <TabsContent value="db"><DbHealthTab /></TabsContent>
                <TabsContent value="integrity"><AuditIntegrityTab /></TabsContent>
                <TabsContent value="policies"><AuditPoliciesTab /></TabsContent>
                <TabsContent value="reports"><AuditReportsTab /></TabsContent>
                <TabsContent value="engine"><EngineTab /></TabsContent>
                <TabsContent value="import"><BulkImportTab /></TabsContent>
            </Tabs>
        </div>
    );
}
