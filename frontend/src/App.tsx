import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { AppShell } from './components/layout/AppShell';
import { ProtectedRoute } from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import RulesPage from './pages/RulesPage';
import CreateRulePage from './pages/CreateRulePage';
import EditRulePage from './pages/EditRulePage';
import TestSandboxPage from './pages/TestSandboxPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import MetricsPage from './pages/MetricsPage';
import ConflictsPage from './pages/ConflictsPage';
import AdminPage from './pages/AdminPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<HomePage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/rules/create" element={<CreateRulePage />} />
            <Route path="/rules/:id/edit" element={<EditRulePage />} />
            <Route path="/test" element={<TestSandboxPage />} />
            <Route path="/diagnostics" element={<DiagnosticsPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/conflicts" element={<ConflictsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </QueryClientProvider>
  );
}
