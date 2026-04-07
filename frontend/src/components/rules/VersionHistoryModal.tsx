import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rulesApi } from '../../api/rules';
import { VersionDiff } from './VersionDiff';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { formatDate } from '../../lib/utils';
import type { RuleVersionDiff } from '../../types/rule';
import { Maximize2, Minimize2 } from 'lucide-react';

interface VersionHistoryModalProps {
    ruleId: number;
    open: boolean;
    onClose: () => void;
}

export function VersionHistoryModal({ ruleId, open, onClose }: VersionHistoryModalProps) {
    const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
    const [diffData, setDiffData] = useState<RuleVersionDiff | null>(null);
    const [diffLoading, setDiffLoading] = useState(false);
    const [maximized, setMaximized] = useState(false);

    const { data: versions, isLoading } = useQuery({
        queryKey: ['versions', ruleId],
        queryFn: () => rulesApi.versions(ruleId).then((r) => r.data),
        enabled: open,
    });

    const loadDiff = async (version: number) => {
        if (version <= 1) return;
        setSelectedVersion(version);
        setDiffLoading(true);
        try {
            const res = await rulesApi.versionDiff(ruleId, version - 1, version);
            setDiffData(res.data);
        } catch {
            setDiffData(null);
        } finally {
            setDiffLoading(false);
        }
    };

    const handleClose = () => {
        setSelectedVersion(null);
        setDiffData(null);
        setMaximized(false);
        onClose();
    };

    return (
        <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
            <DialogContent className={maximized ? 'max-w-[95vw] w-[95vw] max-h-[95vh]' : 'max-w-2xl'}>
                <DialogHeader>
                    <div className="flex items-center justify-between pr-6">
                        <DialogTitle>Version History</DialogTitle>
                        <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => setMaximized((m) => !m)}
                            className="h-7 w-7"
                        >
                            {maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                        </Button>
                    </div>
                </DialogHeader>

                {isLoading && <p className="text-muted-foreground text-sm py-4">Loading versions…</p>}

                {versions && versions.length === 0 && (
                    <p className="text-muted-foreground text-sm py-4">No versions found.</p>
                )}

                {/* UI-only: refined version list with better active state */}
                {versions && versions.length > 0 && (
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                        {versions.map((v) => (
                            <div
                                key={v.version}
                                onClick={() => loadDiff(v.version)}
                                className={`cursor-pointer rounded-lg px-3.5 py-2.5 border transition-all duration-150 text-sm ${selectedVersion === v.version
                                    ? 'border-primary/50 bg-primary/10 shadow-sm'
                                    : 'border-border/40 hover:bg-muted/40 hover:border-border'
                                    }`}
                            >
                                <span className="font-semibold text-foreground">Version {v.version}</span>
                                <span className="ml-3 text-muted-foreground text-xs">{formatDate(v.created_at)}</span>
                                {v.version > 1 && (
                                    <span className="ml-2 text-xs text-primary/70">(click to diff)</span>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {diffLoading && <p className="text-muted-foreground text-sm mt-3">Loading diff…</p>}

                {diffData && !diffLoading && (
                    <div className="mt-5 space-y-3 animate-fade-in">
                        <h4 className="font-semibold text-sm text-foreground">
                            Differences: v{diffData.version1} → v{diffData.version2}
                        </h4>
                        <VersionDiff
                            differences={diffData.differences}
                            v1Label={`v${diffData.version1}`}
                            v2Label={`v${diffData.version2}`}
                        />
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
