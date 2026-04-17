import { Button } from '../ui/button';
import { Input } from '../ui/input';
import type { IntentPattern, PrimitiveValue } from '../../types/rule';

const OPERATOR_OPTIONS = ['==', '!=', '>', '>=', '<', '<=', 'contains', 'in'] as const;

interface IntentPatternPickerProps {
    label: string;
    value: IntentPattern;
    onChange: (next: IntentPattern) => void;
}

function parseValue(raw: string): PrimitiveValue {
    const trimmed = raw.trim();
    if (trimmed.length === 0) return '';
    if (trimmed === 'null') return null;
    if (trimmed === 'true') return true;
    if (trimmed === 'false') return false;

    const numeric = Number(trimmed);
    if (!Number.isNaN(numeric) && trimmed !== '') {
        return numeric;
    }

    return raw;
}

function stringifyValue(value: PrimitiveValue): string {
    if (value === null) return 'null';
    return String(value);
}

export function IntentPatternPicker({ label, value, onChange }: IntentPatternPickerProps) {
    const updateIntent = (intent: string) => onChange({ ...value, intent });

    const updatePredicate = (
        idx: number,
        key: 'field' | 'op' | 'value',
        rawValue: string,
    ) => {
        const where = [...value.where];
        const current = where[idx];
        where[idx] = {
            ...current,
            [key]: key === 'value' ? parseValue(rawValue) : rawValue,
        };
        onChange({ ...value, where });
    };

    const addPredicate = () => {
        onChange({
            ...value,
            where: [...value.where, { field: '', op: '==', value: '' }],
        });
    };

    const removePredicate = (idx: number) => {
        onChange({
            ...value,
            where: value.where.filter((_, currentIdx) => currentIdx !== idx),
        });
    };

    return (
        <div className="border border-border/50 rounded-xl p-4 space-y-3">
            <div>
                <label className="text-sm font-medium text-foreground">{label}</label>
                <Input
                    value={value.intent}
                    onChange={(event) => updateIntent(event.target.value)}
                    placeholder="transaction_authorized"
                    className="mt-1.5"
                />
            </div>

            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">Optional predicates</p>
                    <Button type="button" size="sm" variant="outline" onClick={addPredicate}>+ Predicate</Button>
                </div>

                {value.where.map((predicate, idx) => (
                    <div key={`${label}-${idx}`} className="grid grid-cols-[1fr_130px_1fr_auto] gap-2 items-center">
                        <Input
                            value={predicate.field}
                            onChange={(event) => updatePredicate(idx, 'field', event.target.value)}
                            placeholder="field"
                        />
                        <select
                            value={predicate.op}
                            onChange={(event) => updatePredicate(idx, 'op', event.target.value)}
                            className="native-select"
                        >
                            {OPERATOR_OPTIONS.map((operator) => (
                                <option key={operator} value={operator}>{operator}</option>
                            ))}
                        </select>
                        <Input
                            value={stringifyValue(predicate.value)}
                            onChange={(event) => updatePredicate(idx, 'value', event.target.value)}
                            placeholder="value"
                        />
                        <Button type="button" size="sm" variant="ghost" onClick={() => removePredicate(idx)}>Remove</Button>
                    </div>
                ))}
            </div>
        </div>
    );
}
