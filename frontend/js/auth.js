const API_BASE = '/api/v1';

function getToken() {
    return localStorage.getItem('token');
}

function setToken(token) {
    localStorage.setItem('token', token);
}

function removeToken() {
    localStorage.removeItem('token');
}

function isAuthenticated() {
    return !!getToken();
}

async function login(username, password) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${API_BASE}/auth/token`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData
    });

    if (!response.ok) {
        throw new Error('Invalid credentials');
    }

    const data = await response.json();
    setToken(data.access_token);
    return data;
}

async function register(username, email, password, role) {
    const response = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, email, password, role })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Registration failed');
    }

    return response.json();
}

function logout() {
    removeToken();
    window.location.href = 'login.html';
}

async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    
    console.log('fetchWithAuth called:', url);
    console.log('Token exists:', !!token);
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    } else {
        console.warn('No token found! Redirecting to login...');
        removeToken();
        window.location.href = 'login.html';
        throw new Error('No authentication token');
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        console.log('Response status:', response.status);

        if (response.status === 401) {
            console.error('Unauthorized - token may be expired');
            removeToken();
            window.location.href = 'login.html';
            throw new Error('Unauthorized');
        }

        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

if (window.location.pathname.endsWith('login.html')) {
    document.getElementById('login-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorEl = document.getElementById('login-error');

        try {
            await login(username, password);
            console.log('Login successful, redirecting...');
            window.location.href = 'index.html';
        } catch (error) {
            console.error('Login error:', error);
            errorEl.textContent = error.message;
        }
    });

    document.getElementById('register-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('reg-username').value;
        const email = document.getElementById('reg-email').value;
        const password = document.getElementById('reg-password').value;
        const role = document.getElementById('reg-role').value;
        const errorEl = document.getElementById('register-error');

        try {
            await register(username, email, password, role);
            document.querySelector('.register-box').style.display = 'none';
            document.querySelector('.login-box').style.display = 'block';
            alert('Registration successful! Please login.');
        } catch (error) {
            console.error('Registration error:', error);
            errorEl.textContent = error.message;
        }
    });

    document.getElementById('show-register')?.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('.login-box').style.display = 'none';
        document.querySelector('.register-box').style.display = 'block';
    });

    document.getElementById('show-login')?.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelector('.register-box').style.display = 'none';
        document.querySelector('.login-box').style.display = 'block';
    });
}