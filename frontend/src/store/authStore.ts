import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
    token: string | null;
    username: string | null;
    role: string | null;
    setAuth: (token: string, username: string, role?: string) => void;
    clearAuth: () => void;
    isAuthenticated: () => boolean;
    isAdmin: () => boolean;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            token: null,
            username: null,
            role: null,
            setAuth: (token, username, role = 'business') => {
                set({ token, username, role });
                // Keep legacy keys for backward compat with old frontend
                localStorage.setItem('token', token);
                localStorage.setItem('username', username);
            },
            clearAuth: () => {
                set({ token: null, username: null, role: null });
                localStorage.removeItem('token');
                localStorage.removeItem('username');
            },
            isAuthenticated: () => !!get().token,
            isAdmin: () => get().role === 'admin',
        }),
        { name: 'auth-storage' }
    )
);
