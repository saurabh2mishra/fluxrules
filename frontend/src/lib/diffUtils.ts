import { diffLines } from 'diff';

export interface DiffLine {
    value: string;
    added?: boolean;
    removed?: boolean;
}

export function toDiffString(value: unknown): string {
    if (typeof value === 'string') return value;
    if (value == null) return String(value);
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
}

export function computeLineDiff(previousValue: string, nextValue: string): DiffLine[] {
    return diffLines(previousValue, nextValue).flatMap((part) => {
        const normalized = part.value.endsWith('\n') ? part.value.slice(0, -1) : part.value;
        if (normalized.length === 0) return [];
        return normalized.split('\n').map((line) => ({
            value: line,
            added: part.added,
            removed: part.removed,
        }));
    });
}
