import { useEffect, useState } from 'react';
import { Input } from '../ui/input';
import type { AccumulateDSL, TimeWindowUnit } from '../../types/rule';

interface ThresholdAlertFormProps {
    value?: AccumulateDSL;
    onChange: (next: AccumulateDSL) => void;
}

const DEFAULT_VALUE: AccumulateDSL = {
    type: 'accumulate',
    source_event: '',
    metric_field: '',
    metric_op: '>=',
    threshold: 0,
    window: {
        value: 5,
        unit: 'minutes',
    },
    group_by: [],
};

export function ThresholdAlertForm({ value = DEFAULT_VALUE, onChange }: ThresholdAlertFormProps) {
    const [local, setLocal] = useState<AccumulateDSL>(value);

    useEffect(() => {
        onChange(local);
    }, [local, onChange]);

    const update = <K extends keyof AccumulateDSL>(key: K, nextValue: AccumulateDSL[K]) => {
        setLocal((prev) => ({ ...prev, [key]: nextValue }));
    };

    const updateWindow = (key: 'value' | 'unit', nextValue: number | TimeWindowUnit) => {
        setLocal((prev) => ({
            ...prev,
            window: {
                ...prev.window,
                [key]: nextValue,
            },
        }));
    };

    return (
        <div className="space-y-4 border border-border/50 rounded-xl p-5 bg-card/50">
            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="text-sm font-medium text-foreground">Source event</label>
                    <Input value={local.source_event} onChange={(event) => update('source_event', event.target.value)} className="mt-1.5" />
                </div>
                <div>
                    <label className="text-sm font-medium text-foreground">Metric field</label>
                    <Input value={local.metric_field} onChange={(event) => update('metric_field', event.target.value)} className="mt-1.5" />
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
                <div>
                    <label className="text-sm font-medium text-foreground">Operator</label>
                    <select
                        value={local.metric_op}
                        onChange={(event) => update('metric_op', event.target.value as AccumulateDSL['metric_op'])}
                        className="native-select mt-1.5 w-full"
                    >
                        {['>', '>=', '<', '<=', '==', '!='].map((op) => (
                            <option key={op} value={op}>{op}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="text-sm font-medium text-foreground">Threshold</label>
                    <Input type="number" value={local.threshold} onChange={(event) => update('threshold', Number(event.target.value) || 0)} className="mt-1.5" />
                </div>
                <div>
                    <label className="text-sm font-medium text-foreground">Window (size)</label>
                    <Input type="number" min={1} value={local.window.value} onChange={(event) => updateWindow('value', Number(event.target.value) || 1)} className="mt-1.5" />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="text-sm font-medium text-foreground">Window (unit)</label>
                    <select
                        value={local.window.unit}
                        onChange={(event) => updateWindow('unit', event.target.value as TimeWindowUnit)}
                        className="native-select mt-1.5 w-full"
                    >
                        <option value="minutes">minutes</option>
                        <option value="hours">hours</option>
                        <option value="days">days</option>
                    </select>
                </div>
                <div>
                    <label className="text-sm font-medium text-foreground">Group by fields (comma-separated)</label>
                    <Input
                        value={local.group_by.join(', ')}
                        onChange={(event) => update('group_by', event.target.value.split(',').map((v) => v.trim()).filter(Boolean))}
                        className="mt-1.5"
                    />
                </div>
            </div>
        </div>
    );
}
