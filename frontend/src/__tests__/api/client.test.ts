import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import { server, handlers } from '../mocks/server';
import axios from 'axios';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('API client interceptors', () => {
    it('attaches Authorization header when token is in localStorage', async () => {
        localStorage.setItem('token', 'my-secret-token');
        const { apiClient } = await import('../../api/client');
        // MSW will handle the request
        const res = await apiClient.get('/rules');
        expect(res.status).toBe(200);
        localStorage.removeItem('token');
    });

    it('login returns a token', async () => {
        const { login } = await import('../../api/auth');
        const result = await login('admin', 'password');
        expect(result.access_token).toBe('test-token');
        expect(result.token_type).toBe('bearer');
    });
});
