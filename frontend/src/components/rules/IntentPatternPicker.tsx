import { Input } from '../ui/input';

interface IntentPatternPickerProps {
    value: string;
    onChange: (value: string) => void;
}

export function IntentPatternPicker({ value, onChange }: IntentPatternPickerProps) {
    return (
        <div className="space-y-3">
            <div>
                <label className="text-sm font-medium text-foreground">Intent Pattern</label>
                <Input
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder="payments.high_value"
                    className="mt-1.5"
                />
            </div>
            <p className="text-xs text-muted-foreground">
                Choose an intent pattern key. The rule builder maps this pattern into canonical DSL conditions automatically.
            </p>
        </div>
    );
}
