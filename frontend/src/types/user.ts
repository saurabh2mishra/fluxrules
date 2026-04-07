export interface Token {
    access_token: string;
    token_type: string;
    role?: string;
}

export interface UserCreate {
    username: string;
    email: string;
    password: string;
    role: 'business' | 'admin';
}

export interface UserResponse {
    id: number;
    username: string;
    email: string;
    role: string;
}
