import { useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { IntentPatternPicker } from './IntentPatternPicker';
import type { CrossFactJoinDSL } from '../../types/rule';

interface CombinationMatchFormProps {
    value?: CrossFactJoinDSL;
    onChange: (next: CrossFactJoinDSL) => void;
}

const DEFAULT_VALUE: CrossFactJoinDSL = {
    type: 'cross_fact_join',
    left: { intent: '', where: [] },
    right: { intent: '', where: [] },
    join_on: [{ left_field: '', right_field: '' }],
    match: 'all',
};

export function CombinationMatchForm({ value = DEFAULT_VALUE, onChange }: CombinationMatchFormProps) {
    const [local, setLocal] = useState<CrossFactJoinDSL>(value);

    useEffect(() => {
        onChange(local);
    }, [local, onChange]);

    const updateJoin = (idx: number, key: 'left_field' | 'right_field', nextValue: string) => {
        setLocal((prev) => {
            const join_on = [...prev.join_on];
            join_on[idx] = { ...join_on[idx], [key]: nextValue };
            return { ...prev, join_on };
        });
    };

    return (
        <div className="space-y-4 border border-border/50 rounded-xl p-5 bg-card/50">
            <IntentPatternPicker
                label="Left intent"
                value={local.left}
                onChange={(next) => setLocal((prev) => ({ ...prev, left: next }))}
            />
            <IntentPatternPicker
                label="Right intent"
                value={local.right}
                onChange={(next) => setLocal((prev) => ({ ...prev, right: next }))}
            />

            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground">Join fields</label>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setLocal((prev) => ({
                            ...prev,
                            join_on: [...prev.join_on, { left_field: '', right_field: '' }],
                        }))}
                    >
                        + Join key
                    </Button>
                </div>

                {local.join_on.map((pair, idx) => (
                    <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
                        <Input
                            value={pair.left_field}
                            onChange={(event) => updateJoin(idx, 'left_field', event.target.value)}
                            placeholder="left field"
                        />
                        <Input
                            value={pair.right_field}
                            onChange={(event) => updateJoin(idx, 'right_field', event.target.value)}
                            placeholder="right field"
                        />
                        <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => setLocal((prev) => ({
                                ...prev,
                                join_on: prev.join_on.filter((_, currentIdx) => currentIdx !== idx),
                            }))}
                            disabled={local.join_on.length === 1}
                        >
                            Remove
                        </Button>
                    </div>
                ))}
            </div>

            <div>
                <label className="text-sm font-medium text-foreground">Join match mode</label>
                <select
                    value={local.match}
                    onChange={(event) => setLocal((prev) => ({ ...prev, match: event.target.value as CrossFactJoinDSL['match'] }))}
                    className="native-select mt-1.5 w-full"
                >
                    <option value="all">all</option>
                    <option value="any">any</option>
                </select>
            </div>
        </div>
    );
}
