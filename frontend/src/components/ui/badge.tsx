import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

/* UI-only: softer badge variants — pill shape, calmer colors, improved light-mode contrast */
const badgeVariants = cva(
    'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
    {
        variants: {
            variant: {
                default: 'border-primary/20 bg-primary/15 text-primary',
                secondary: 'border-border bg-muted text-foreground/70',
                destructive: 'border-red-200 bg-red-100 text-red-800 dark:border-red-800/30 dark:bg-red-900/25 dark:text-red-400',
                success: 'border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-800/30 dark:bg-emerald-900/25 dark:text-emerald-400',
                warning: 'border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-800/30 dark:bg-amber-900/25 dark:text-amber-400',
                outline: 'border-border text-foreground/70',
            },
        },
        defaultVariants: { variant: 'default' },
    }
);

export interface BadgeProps
    extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> { }

function Badge({ className, variant, ...props }: BadgeProps) {
    return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
