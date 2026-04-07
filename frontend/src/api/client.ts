import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

export const apiClient = axios.create({ baseURL: API_BASE });

// Read token from either the Zustand persist key or the legacy key
function getToken(): string | null {
    // Primary: Zustand persist key (survives page reloads)
    try {
        const stored = localStorage.getItem('auth-storage');
        if (stored) {
            const parsed = JSON.parse(stored);
            const token = parsed?.state?.token;
            if (token) return token;
        }
    } catch { /* ignore parse errors */ }
    // Fallback: legacy key written by setAuth()
    return localStorage.getItem('token');
}

// Inject Bearer token on every request
apiClient.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Redirect to /login on 401
apiClient.interceptors.response.use(
    (res) => res,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('username');
            localStorage.removeItem('auth-storage');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);
