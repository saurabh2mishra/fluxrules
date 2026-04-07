import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { List, PlusCircle, FlaskConical, BarChart3, Network, ArrowRight } from 'lucide-react';

const PHRASES = ['Simple, but Fast!', 'Built for Speed.', 'Easy to Use.'];

// Each phrase gets its own gradient — cycles with the phrase index
const PHRASE_COLORS = [
    'from-violet-500 to-indigo-500',   // Simple, but Fast!
    'from-emerald-500 to-teal-400',    // Built for Speed.
    'from-amber-400 to-orange-500',    // Easy to Use.
];

function useTypingAnimation() {
    const [text, setText] = useState('');
    const [phraseIdx, setPhraseIdx] = useState(0);
    const phraseIdxRef = useRef(0);
    const charIdx = useRef(0);
    const deleting = useRef(false);

    useEffect(() => {
        let timeout: ReturnType<typeof setTimeout>;
        const tick = () => {
            const phrase = PHRASES[phraseIdxRef.current];
            if (!deleting.current) {
                setText(phrase.substring(0, charIdx.current + 1));
                charIdx.current++;
                if (charIdx.current === phrase.length) {
                    deleting.current = true;
                    timeout = setTimeout(tick, 2000);
                    return;
                }
            } else {
                setText(phrase.substring(0, charIdx.current - 1));
                charIdx.current--;
                if (charIdx.current === 0) {
                    deleting.current = false;
                    phraseIdxRef.current = (phraseIdxRef.current + 1) % PHRASES.length;
                    setPhraseIdx(phraseIdxRef.current);
                    timeout = setTimeout(tick, 500);
                    return;
                }
            }
            timeout = setTimeout(tick, deleting.current ? 50 : 100);
        };
        timeout = setTimeout(tick, 100);
        return () => clearTimeout(timeout);
    }, []);

    return { text, phraseIdx };
}

const QUICK_LINKS = [
    { icon: List, label: 'View Rules', description: 'Browse & manage all rules', to: '/rules', color: 'text-blue-500', bg: 'bg-blue-500/10' },
    { icon: PlusCircle, label: 'Create Rule', description: 'Build new rule logic', to: '/rules/create', color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { icon: FlaskConical, label: 'Test Sandbox', description: 'Simulate event matching', to: '/test', color: 'text-violet-500', bg: 'bg-violet-500/10' },
    { icon: BarChart3, label: 'Metrics', description: 'Performance analytics', to: '/metrics', color: 'text-amber-500', bg: 'bg-amber-500/10' },
];

export default function HomePage() {
    const { text: typed, phraseIdx } = useTypingAnimation();
    const navigate = useNavigate();

    return (
        <div className="flex flex-col items-center justify-center min-h-[65vh] text-center px-4 animate-fade-in">
            {/* Hero */}
            <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 mb-5">
                <Network size={28} className="text-primary" />
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold text-foreground mb-3 tracking-tight">FluxRules</h1>
            <p className="text-muted-foreground text-base sm:text-lg max-w-xl mb-2 leading-relaxed">
                A high-performance rule management platform.
            </p>
            <p className="text-lg sm:text-xl font-semibold min-h-[2rem] mb-10 transition-all duration-700">
                <span className={`bg-gradient-to-r ${PHRASE_COLORS[phraseIdx]} bg-clip-text text-transparent`}>
                    {typed}
                </span>
                <span className={`cursor-blink ml-0.5 bg-gradient-to-r ${PHRASE_COLORS[phraseIdx]} bg-clip-text text-transparent opacity-60`}>|</span>
            </p>

            {/* Quick links */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 w-full max-w-2xl">
                {QUICK_LINKS.map((link) => (
                    <button
                        key={link.to}
                        onClick={() => navigate(link.to)}
                        className="flex flex-col items-center gap-3 p-5 rounded-xl border border-border/50 bg-card hover:shadow-card-hover hover:border-border transition-all duration-200 cursor-pointer group text-left"
                    >
                        <div className={`w-10 h-10 rounded-xl ${link.bg} flex items-center justify-center group-hover:scale-110 transition-transform duration-200`}>
                            <link.icon size={20} className={link.color} />
                        </div>
                        <div className="text-center">
                            <span className="text-sm font-medium block">{link.label}</span>
                            <span className="text-[0.6875rem] text-muted-foreground mt-0.5 block">{link.description}</span>
                        </div>
                    </button>
                ))}
            </div>

            <Button className="mt-10 gap-2" onClick={() => navigate('/rules/create')}>
                <PlusCircle size={16} /> Create your first rule <ArrowRight size={14} />
            </Button>
        </div>
    );
}
