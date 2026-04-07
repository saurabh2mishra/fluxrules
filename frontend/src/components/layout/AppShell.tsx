import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar, SidebarContent } from './Sidebar';
import { useDarkMode } from '../../hooks/useDarkMode';
import { cn } from '../../lib/utils';
import { Sheet, SheetContent } from '../ui/sheet';
import { Menu, Network } from 'lucide-react';
import { Button } from '../ui/button';

export function AppShell() {
    useDarkMode(); // ensure dark class is synced on mount
    const [mobileOpen, setMobileOpen] = useState(false);

    return (
        <div className={cn('flex h-screen overflow-hidden bg-background')}>
            {/* Desktop sidebar */}
            <div className="hidden md:flex">
                <Sidebar />
            </div>

            {/* Mobile sidebar (Sheet) */}
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetContent side="left" className="p-0 w-60">
                    <SidebarContent onNavigate={() => setMobileOpen(false)} />
                </SheetContent>
            </Sheet>

            <main className="flex-1 overflow-y-auto bg-background">
                {/* Mobile top bar */}
                <div className="flex md:hidden items-center gap-3 px-4 py-3 border-b border-border/60 bg-card/80 backdrop-blur-sm sticky top-0 z-10">
                    <Button variant="ghost" size="sm" onClick={() => setMobileOpen(true)} className="shrink-0">
                        <Menu size={18} />
                    </Button>
                    <div className="flex items-center gap-2">
                        <Network size={14} className="text-primary" />
                        <span className="font-bold text-foreground">FluxRules</span>
                    </div>
                </div>
                {/* Page content with refined spacing */}
                <div className="p-5 md:p-8 max-w-[1400px] min-h-full">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
