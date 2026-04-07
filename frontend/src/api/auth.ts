import axios from 'axios';
import { API_BASE } from './client';
import type { Token, UserCreate, UserResponse } from '../types/user';

export async function login(username: string, password: string): Promise<Token> {
    const params = new URLSearchParams({ username, password });
    const res = await axios.post<Token>(`${API_BASE}/auth/token`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return res.data;
}

export async function register(body: UserCreate): Promise<UserResponse> {
    const res = await axios.post<UserResponse>(`${API_BASE}/auth/register`, body);
    return res.data;
}
