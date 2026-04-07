import { cn } from '../../lib/utils';

interface SpinnerProps {
    size?: 'sm' | 'md' | 'lg';
    className?: string;
}

/* UI-only: refined spinner — softer border colors */
export function Spinner({ size = 'md', className }: SpinnerProps) {
    const sizes = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-10 w-10' };
    return (
        <div
            className={cn(
                'animate-spin rounded-full border-2 border-muted/60 border-t-primary',
                sizes[size],
                className
            )}
        />
    );
}

export function FullPageSpinner() {
    return (
        <div className="flex h-full min-h-[300px] w-full items-center justify-center animate-fade-in">
            <Spinner size="lg" />
        </div>
    );
}
