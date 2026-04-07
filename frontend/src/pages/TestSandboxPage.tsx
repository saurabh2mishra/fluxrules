import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { rulesApi } from '../api/rules';
import { Button } from '../components/ui/button';
import { JsonEditor } from '../components/ui/json-editor';
import type { SimulateResponse } from '../types/rule';
import { Play, Trash2, Lightbulb, FlaskConical } from 'lucide-react';

const EXAMPLE_EVENT = {
    amount: 15000,
    type: 'transfer',
    country: 'US',
    user_id: 'user_12345',
    account_age: 30,
};

export default function TestSandboxPage() {
    const [eventText, setEventText] = useState('');
    const [result, setResult] = useState<SimulateResponse | null>(null);
    const [parseError, setParseError] = useState('');

    const simulateMutation = useMutation({
        mutationFn: (event: Record<string, unknown>) => rulesApi.simulate(event).then((r) => r.data),
        onSuccess: (data) => { setResult(data); setParseError(''); },
        onError: () => setParseError('Server error during simulation'),
    });

    const handleRun = () => {
        setParseError('');
        if (!eventText.trim()) { setParseError('Please enter a JSON event'); return; }
        try {
            const event = JSON.parse(eventText);
            simulateMutation.mutate(event);
        } catch (e) {
            setParseError(`Invalid JSON: ${(e as Error).message}`);
        }
    };

    const handleClear = () => {
        setEventText('');
        setResult(null);
        setParseError('');
    };

    const handleExample = () => {
        setEventText(JSON.stringify(EXAMPLE_EVENT, null, 2));
        setResult(null);
        setParseError('');
    };

    return (
        <div className="max-w-3xl animate-fade-in">
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
                <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-violet-500/10">
                    <FlaskConical size={18} className="text-violet-500" />
                </div>
                <h1 className="text-xl font-bold text-foreground">Test Sandbox</h1>
            </div>
            <p className="text-muted-foreground text-sm mb-6 ml-12">
                Simulate a JSON event against your rules and see which ones match.
            </p>

            {/* Event input panel */}
            <div className="border border-border/50 rounded-xl p-5 mb-5 bg-card/50">
                <div className="flex items-center justify-between mb-3">
                    <label className="text-sm font-medium text-foreground">Event JSON</label>
                    <Button size="sm" variant="ghost" onClick={handleExample} className="text-xs">
                        <Lightbulb size={13} /> Insert Example
                    </Button>
                </div>
                <JsonEditor
                    value={eventText}
                    onChange={(val) => setEventText(val)}
                    height="280px"
                />
                {parseError && <p className="text-xs text-red-500 mt-2">{parseError}</p>}
            </div>

            <div className="flex gap-3 mb-8">
                <Button onClick={handleRun} disabled={simulateMutation.isPending}>
                    <Play size={14} /> {simulateMutation.isPending ? 'Running…' : 'Run Test'}
                </Button>
                <Button variant="outline" onClick={handleClear}>
                    <Trash2 size={14} /> Clear
                </Button>
            </div>

            {/* Results */}
            {result && (
                <div className="space-y-4 animate-fade-in">
                    {result.stats && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            {[
                                ['Total Rules', result.stats.total_rules, 'text-foreground'],
                                ['Evaluated', result.stats.candidates_evaluated, 'text-foreground'],
                                ['Time', `${result.stats.evaluation_time_ms}ms`, 'text-primary'],
                                ['Engine', result.stats.optimization, 'text-foreground'],
                            ].map(([label, val, color]) => (
                                <div key={label as string} className="border border-border/50 rounded-xl p-4 text-center bg-card">
                                    <div className={`font-bold text-lg ${color}`}>{val}</div>
                                    <div className="text-[0.6875rem] text-muted-foreground mt-1">{label}</div>
                                </div>
                            ))}
                        </div>
                    )}

                    {result.matched_rules.length === 0 ? (
                        <div className="border border-border/50 rounded-xl p-8 text-center text-muted-foreground bg-card/50">
                            <p className="font-semibold text-base">📭 No Rules Matched</p>
                            <p className="text-sm mt-1">Try modifying your event data or check your rule conditions.</p>
                        </div>
                    ) : (
                        <>
                            <p className="font-semibold text-emerald-600 dark:text-emerald-400">
                                ✅ {result.matched_rules.length} Rule(s) Matched
                            </p>
                            {result.matched_rules.map((rule, i) => (
                                <div key={rule.id} className="border border-border/50 rounded-xl p-5 bg-card">
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <span className="w-7 h-7 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-bold">
                                            {i + 1}
                                        </span>
                                        <span className="font-semibold text-foreground">{rule.name}</span>
                                        <span className="text-xs text-muted-foreground ml-auto">Priority: {rule.priority}</span>
                                    </div>
                                    <p className="text-sm">
                                        <span className="text-muted-foreground">Action: </span>
                                        <code className="bg-muted/60 px-1.5 py-0.5 rounded-md text-xs font-mono">{rule.action}</code>
                                    </p>
                                    {result.explanations?.[rule.id] && (
                                        <p className="text-xs text-muted-foreground mt-2 font-mono bg-muted/30 p-2 rounded-lg">
                                            {result.explanations[rule.id]}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
