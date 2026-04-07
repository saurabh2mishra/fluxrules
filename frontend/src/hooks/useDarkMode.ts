import { useEffect } from 'react';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const useDarkStore = create<{ dark: boolean; toggle: () => void }>()(
    persist(
        (set, get) => ({
            dark: false,
            toggle: () => set({ dark: !get().dark }),
        }),
        { name: 'dark-mode' }
    )
);

export function useDarkMode() {
    const { dark, toggle } = useDarkStore();

    useEffect(() => {
        if (dark) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
    }, [dark]);

    return { dark, toggle };
}
