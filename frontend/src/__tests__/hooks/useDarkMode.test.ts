import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Minimal test: we can't fully test DOM class list in jsdom without extra setup,
// but we can verify the state toggle.
describe('useDarkMode', () => {
    it('toggles dark state', async () => {
        const { useDarkMode } = await import('../../hooks/useDarkMode');
        const { result } = renderHook(() => useDarkMode());

        expect(result.current.dark).toBe(false);

        act(() => result.current.toggle());
        expect(result.current.dark).toBe(true);

        act(() => result.current.toggle());
        expect(result.current.dark).toBe(false);
    });
});
