import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { login, register } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useDarkMode } from '../hooks/useDarkMode';
import { Network } from 'lucide-react';

const loginSchema = z.object({
    username: z.string().min(1, 'Username is required'),
    password: z.string().min(1, 'Password is required'),
});

const registerSchema = z.object({
    username: z.string().min(1, 'Username is required'),
    email: z.string().email('Valid email required'),
    password: z.string()
        .min(8, 'Min 8 characters')
        .regex(/[A-Z]/, 'Need uppercase')
        .regex(/[a-z]/, 'Need lowercase')
        .regex(/[0-9]/, 'Need digit'),
    role: z.enum(['business', 'admin']),
});

type LoginForm = z.infer<typeof loginSchema>;
type RegisterForm = z.infer<typeof registerSchema>;

export default function LoginPage() {
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const { setAuth } = useAuthStore();
    const navigate = useNavigate();
    useDarkMode();

    const loginForm = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });
    const registerForm = useForm<RegisterForm>({
        resolver: zodResolver(registerSchema),
        defaultValues: { role: 'business' },
    });

    const onLogin = async (data: LoginForm) => {
        try {
            const token = await login(data.username, data.password);
            setAuth(token.access_token, data.username, token.role || 'business');
            navigate('/');
        } catch {
            loginForm.setError('password', { message: 'Invalid username or password' });
        }
    };

    const onRegister = async (data: RegisterForm) => {
        try {
            await register(data);
            setMode('login');
            registerForm.reset();
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Registration failed';
            registerForm.setError('username', { message: msg });
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            {/* Subtle background pattern */}
            <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/[0.03] via-transparent to-transparent pointer-events-none" />

            <div className="w-full max-w-sm relative z-10 animate-slide-up">
                {/* Card */}
                <div className="bg-card border border-border/50 rounded-2xl shadow-lg p-8">
                    {/* Brand */}
                    <div className="flex flex-col items-center mb-6">
                        <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-primary/10 mb-3">
                            <Network size={22} className="text-primary" />
                        </div>
                        <h1 className="text-xl font-bold text-foreground tracking-tight">FluxRules</h1>
                        <p className="text-muted-foreground text-sm mt-1">
                            {mode === 'login' ? 'Sign in to your account' : 'Create a new account'}
                        </p>
                    </div>

                    {mode === 'login' ? (
                        <form onSubmit={loginForm.handleSubmit(onLogin)} className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-foreground">Username</label>
                                <Input {...loginForm.register('username')} placeholder="admin" className="mt-1.5" />
                                {loginForm.formState.errors.username && (
                                    <p className="text-xs text-red-500 mt-1">{loginForm.formState.errors.username.message}</p>
                                )}
                            </div>
                            <div>
                                <label className="text-sm font-medium text-foreground">Password</label>
                                <Input type="password" {...loginForm.register('password')} placeholder="••••••••" className="mt-1.5" />
                                {loginForm.formState.errors.password && (
                                    <p className="text-xs text-red-500 mt-1">{loginForm.formState.errors.password.message}</p>
                                )}
                            </div>
                            <Button
                                type="submit"
                                className="w-full"
                                disabled={loginForm.formState.isSubmitting}
                            >
                                {loginForm.formState.isSubmitting ? 'Signing in…' : 'Sign In'}
                            </Button>
                        </form>
                    ) : (
                        <form onSubmit={registerForm.handleSubmit(onRegister)} className="space-y-4">
                            <div>
                                <label className="text-sm font-medium text-foreground">Username</label>
                                <Input {...registerForm.register('username')} className="mt-1.5" />
                                {registerForm.formState.errors.username && (
                                    <p className="text-xs text-red-500 mt-1">{registerForm.formState.errors.username.message}</p>
                                )}
                            </div>
                            <div>
                                <label className="text-sm font-medium text-foreground">Email</label>
                                <Input type="email" {...registerForm.register('email')} className="mt-1.5" />
                                {registerForm.formState.errors.email && (
                                    <p className="text-xs text-red-500 mt-1">{registerForm.formState.errors.email.message}</p>
                                )}
                            </div>
                            <div>
                                <label className="text-sm font-medium text-foreground">Password</label>
                                <Input type="password" {...registerForm.register('password')} className="mt-1.5" />
                                {registerForm.formState.errors.password && (
                                    <p className="text-xs text-red-500 mt-1">{registerForm.formState.errors.password.message}</p>
                                )}
                            </div>
                            <div>
                                <label className="text-sm font-medium text-foreground">Role</label>
                                <select
                                    {...registerForm.register('role')}
                                    className="native-select mt-1.5 w-full"
                                >
                                    <option value="business">Business User</option>
                                    <option value="admin">Administrator</option>
                                </select>
                            </div>
                            <Button type="submit" className="w-full" disabled={registerForm.formState.isSubmitting}>
                                {registerForm.formState.isSubmitting ? 'Registering…' : 'Register'}
                            </Button>
                        </form>
                    )}

                    <div className="mt-6 text-center text-sm text-muted-foreground">
                        {mode === 'login' ? (
                            <>Don't have an account?{' '}
                                <button onClick={() => setMode('register')} className="text-primary font-medium hover:underline">
                                    Register
                                </button>
                            </>
                        ) : (
                            <>Already have an account?{' '}
                                <button onClick={() => setMode('login')} className="text-primary font-medium hover:underline">
                                    Sign in
                                </button>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
