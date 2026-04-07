import { describe, it, expect } from 'vitest';
import { useAuthStore } from '../../store/authStore';

describe('useAuthStore', () => {
    it('starts unauthenticated', () => {
        const state = useAuthStore.getState();
        expect(state.token).toBeNull();
        expect(state.username).toBeNull();
        expect(state.isAuthenticated()).toBe(false);
    });

    it('setAuth stores token and username', () => {
        useAuthStore.getState().setAuth('test-token', 'admin', 'admin');
        const state = useAuthStore.getState();
        expect(state.token).toBe('test-token');
        expect(state.username).toBe('admin');
        expect(state.role).toBe('admin');
        expect(state.isAuthenticated()).toBe(true);
        expect(state.isAdmin()).toBe(true);
    });

    it('clearAuth resets state', () => {
        useAuthStore.getState().setAuth('tok', 'user1');
        useAuthStore.getState().clearAuth();
        const state = useAuthStore.getState();
        expect(state.token).toBeNull();
        expect(state.username).toBeNull();
        expect(state.isAuthenticated()).toBe(false);
    });

    it('isAdmin returns false for business role', () => {
        useAuthStore.getState().setAuth('tok', 'user1', 'business');
        expect(useAuthStore.getState().isAdmin()).toBe(false);
    });
});
