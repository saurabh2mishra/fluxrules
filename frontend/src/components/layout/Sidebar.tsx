import { NavLink, useNavigate } from 'react-router-dom';
import {
    Home, List, PlusCircle, FlaskConical, Activity,
    BarChart3, AlertTriangle, Settings, LogOut, Moon, Sun,
    Network,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useDarkMode } from '../../hooks/useDarkMode';

const NAV_SECTIONS = [
    {
        label: 'Main',
        items: [
            { to: '/', icon: Home, label: 'Home', end: true },
            { to: '/rules', icon: List, label: 'Rules', end: false },
            { to: '/rules/create', icon: PlusCircle, label: 'Create Rule', end: false },
            { to: '/test', icon: FlaskConical, label: 'Test Sandbox', end: false },
        ],
    },
    {
        label: 'Advanced',
        items: [
            { to: '/diagnostics', icon: Activity, label: 'Diagnostics', end: false },
            { to: '/metrics', icon: BarChart3, label: 'Metrics', end: false },
            { to: '/conflicts', icon: AlertTriangle, label: 'Conflicts', end: false },
        ],
    },
    {
        label: 'System',
        items: [
            { to: '/admin', icon: Settings, label: 'Admin', end: false },
        ],
    },
];

export function Sidebar() {
    return (
        <aside className="w-60 flex-shrink-0 bg-card/80 backdrop-blur-sm border-r border-border/60 flex flex-col h-full">
            <SidebarContent />
        </aside>
    );
}

export function SidebarContent({ onNavigate }: { onNavigate?: () => void } = {}) {
    const { clearAuth, username } = useAuthStore();
    const { dark, toggle } = useDarkMode();
    const navigate = useNavigate();

    const handleLogout = () => {
        clearAuth();
        navigate('/login');
    };

    const handleNavClick = () => {
        onNavigate?.();
    };

    return (
        <div className="flex flex-col h-full">
            {/* Brand */}
            <div className="px-5 py-5 border-b border-border/50">
                <NavLink to="/" className="flex items-center gap-2.5" onClick={handleNavClick}>
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
                        <Network size={16} className="text-primary" />
                    </div>
                    <span className="text-lg font-bold text-foreground tracking-tight">FluxRules</span>
                </NavLink>
            </div>

            {/* Nav */}
            <nav className="flex-1 px-3 py-5 overflow-y-auto space-y-5">
                {NAV_SECTIONS.map((section) => (
                    <div key={section.label}>
                        <p className="text-[0.65rem] font-semibold text-muted-foreground/70 uppercase tracking-widest px-3 mb-2">
                            {section.label}
                        </p>
                        <div className="space-y-0.5">
                            {section.items.map((item) => (
                                <NavLink
                                    key={item.to}
                                    to={item.to}
                                    end={item.end}
                                    onClick={handleNavClick}
                                    className={({ isActive }) =>
                                        `flex items-center gap-3 px-3 py-2 rounded-lg text-[0.8125rem] transition-all duration-150 ${isActive
                                            ? 'bg-primary/10 text-primary font-medium shadow-sm'
                                            : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                                        }`
                                    }
                                >
                                    <item.icon size={16} strokeWidth={isNavActive(item.to) ? 2.5 : 1.75} />
                                    {item.label}
                                </NavLink>
                            ))}
                        </div>
                    </div>
                ))}
            </nav>

            {/* Footer */}
            <div className="px-4 py-4 border-t border-border/50 bg-muted/20">
                <div className="flex items-center gap-3">
                    {/* User avatar */}
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary text-xs font-bold shrink-0">
                        {(username ?? 'U').charAt(0).toUpperCase()}
                    </div>
                    <span className="text-sm text-foreground font-medium truncate flex-1 min-w-0" title={username ?? ''}>
                        {username ?? 'User'}
                    </span>
                    <div className="flex items-center gap-0.5">
                        <button
                            onClick={toggle}
                            className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                            title="Toggle dark mode"
                            aria-label="Toggle dark mode"
                        >
                            {dark ? <Sun size={15} /> : <Moon size={15} />}
                        </button>
                        <button
                            onClick={handleLogout}
                            className="p-1.5 rounded-lg hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                            title="Logout"
                            aria-label="Logout"
                        >
                            <LogOut size={15} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* Helper – not used for logic, purely for icon stroke weight hint.
   NavLink isActive is handled inline above. */
function isNavActive(_to: string): boolean {
    return false; // stroke weight is cosmetic, default fine
}
