import { cn } from '../../lib/utils';
import type { ReactNode } from 'react';

interface EmptyStateProps {
    icon?: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
    className?: string;
}

/* UI-only: refined empty state — calmer icon treatment, improved spacing */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
    return (
        <div className={cn('flex flex-col items-center justify-center py-20 text-center animate-fade-in', className)}>
            {icon && <div className="mb-5 text-muted-foreground/30">{icon}</div>}
            <h3 className="text-base font-semibold text-foreground mb-1.5">{title}</h3>
            {description && <p className="text-sm text-muted-foreground max-w-sm mb-5 leading-relaxed">{description}</p>}
            {action && <div>{action}</div>}
        </div>
    );
}
