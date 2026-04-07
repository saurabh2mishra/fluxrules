import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

/* UI-only: refined button variants — softer shadows, calmer colors, better focus rings */
const buttonVariants = cva(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50',
    {
        variants: {
            variant: {
                default: 'border border-border bg-card text-foreground shadow-sm hover:bg-accent hover:text-accent-foreground',
                destructive: 'bg-red-600 text-white shadow-sm hover:bg-red-600/90 active:bg-red-700',
                outline: 'border border-border bg-card text-foreground shadow-sm hover:bg-accent hover:text-accent-foreground',
                secondary: 'bg-muted text-foreground hover:bg-muted/70',
                ghost: 'text-foreground/70 hover:bg-muted hover:text-foreground',
                link: 'text-foreground underline-offset-4 hover:underline',
                success: 'bg-emerald-600 text-white shadow-sm hover:bg-emerald-600/90 active:bg-emerald-700',
                warning: 'bg-amber-500 text-white shadow-sm hover:bg-amber-500/90 active:bg-amber-600',
            },
            size: {
                default: 'h-9 px-4 py-2',
                sm: 'h-7 rounded-lg px-3 text-xs',
                lg: 'h-11 rounded-lg px-8',
                icon: 'h-9 w-9',
            },
        },
        defaultVariants: {
            variant: 'default',
            size: 'default',
        },
    }
);

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> { }

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, ...props }, ref) => (
        <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
);
Button.displayName = 'Button';

export { Button, buttonVariants };
