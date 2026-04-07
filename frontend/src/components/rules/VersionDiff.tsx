import { computeLineDiff, toDiffString, type DiffLine } from '../../lib/diffUtils';

interface VersionDiffProps {
    differences: Record<string, { version1: unknown; version2: unknown }>;
    v1Label: string;
    v2Label: string;
}

/* UI-only: refined diff block with softer colors */
function DiffBlock({ lines }: { lines: DiffLine[] }) {
    return (
        <pre className="text-xs font-mono leading-relaxed overflow-auto max-h-64 rounded-xl p-3 bg-muted/40 border border-border/30">
            {lines.map((line, i) => (
                <div
                    key={i}
                    className={
                        line.removed
                            ? 'bg-red-500/8 text-red-700 dark:text-red-400'
                            : line.added
                                ? 'bg-emerald-500/8 text-emerald-700 dark:text-emerald-400'
                                : ''
                    }
                >
                    <span className="select-none inline-block w-5 text-right mr-2 text-muted-foreground/40">
                        {line.removed ? '-' : line.added ? '+' : ' '}
                    </span>
                    {line.value}
                </div>
            ))}
        </pre>
    );
}

export function VersionDiff({ differences, v1Label, v2Label }: VersionDiffProps) {
    const fields = Object.keys(differences);

    if (fields.length === 0) {
        return <p className="text-sm text-muted-foreground py-3">No differences found.</p>;
    }

    return (
        <div className="space-y-4">
            {fields.map((field) => {
                const vals = differences[field];
                const oldStr = toDiffString(vals.version1);
                const newStr = toDiffString(vals.version2);
                const lines = computeLineDiff(oldStr, newStr);

                return (
                    <div key={field} className="border border-border/40 rounded-xl p-4">
                        <p className="font-semibold text-sm mb-2.5 text-foreground">{field}</p>

                        {/* Unified diff view */}
                        <DiffBlock lines={lines} />

                        {/* Side-by-side fallback for short values */}
                        {oldStr.split('\n').length <= 3 && newStr.split('\n').length <= 3 && (
                            <div className="grid grid-cols-2 gap-3 mt-3">
                                <div>
                                    <p className="text-xs text-muted-foreground mb-1.5">{v1Label}</p>
                                    <pre className="json-pre diff-old text-xs">{oldStr}</pre>
                                </div>
                                <div>
                                    <p className="text-xs text-muted-foreground mb-1.5">{v2Label}</p>
                                    <pre className="json-pre diff-new text-xs">{newStr}</pre>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
