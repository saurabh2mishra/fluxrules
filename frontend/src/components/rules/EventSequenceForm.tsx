import { useEffect, useState } from 'react';
import { Input } from '../ui/input';
import { IntentPatternPicker } from './IntentPatternPicker';
import type { SequenceDSL, TimeWindowUnit } from '../../types/rule';

interface EventSequenceFormProps {
    value?: SequenceDSL;
    onChange: (next: SequenceDSL) => void;
}

const DEFAULT_VALUE: SequenceDSL = {
    type: 'sequence',
    steps: [
        { intent: '', where: [] },
        { intent: '', where: [] },
    ],
    within: {
        value: 5,
        unit: 'minutes',
    },
};

export function EventSequenceForm({ value = DEFAULT_VALUE, onChange }: EventSequenceFormProps) {
    const [local, setLocal] = useState<SequenceDSL>(value);

    useEffect(() => {
        onChange(local);
    }, [local, onChange]);

    const updateWindow = (key: 'value' | 'unit', nextValue: number | TimeWindowUnit) => {
        setLocal((prev) => ({
            ...prev,
            within: {
                ...prev.within,
                [key]: nextValue,
            },
        }));
    };

    return (
        <div className="space-y-4 border border-border/50 rounded-xl p-5 bg-card/50">
            <IntentPatternPicker
                label="First event"
                value={local.steps[0]}
                onChange={(next) => setLocal((prev) => ({ ...prev, steps: [next, prev.steps[1]] }))}
            />
            <IntentPatternPicker
                label="Followed by"
                value={local.steps[1]}
                onChange={(next) => setLocal((prev) => ({ ...prev, steps: [prev.steps[0], next] }))}
            />

            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="text-sm font-medium text-foreground">Within (size)</label>
                    <Input
                        type="number"
                        min={1}
                        value={local.within.value}
                        onChange={(event) => updateWindow('value', Number(event.target.value) || 1)}
                        className="mt-1.5"
                    />
                </div>
                <div>
                    <label className="text-sm font-medium text-foreground">Within (unit)</label>
                    <select
                        value={local.within.unit}
                        onChange={(event) => updateWindow('unit', event.target.value as TimeWindowUnit)}
                        className="native-select mt-1.5 w-full"
                    >
                        <option value="minutes">minutes</option>
                        <option value="hours">hours</option>
                        <option value="days">days</option>
                    </select>
                </div>
            </div>
        </div>
    );
}
