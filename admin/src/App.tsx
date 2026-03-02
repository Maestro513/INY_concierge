import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminAuthProvider } from '@/auth/AdminAuthProvider';
import ProtectedRoute from '@/auth/ProtectedRoute';
import AdminLayout from '@/layout/AdminLayout';
import LoginPage from '@/pages/login/LoginPage';
import DashboardPage from '@/pages/dashboard/DashboardPage';
import MembersPage from '@/pages/members/MembersPage';
import MemberDetailPage from '@/pages/members/MemberDetailPage';
import PlansPage from '@/pages/plans/PlansPage';
import SystemPage from '@/pages/system/SystemPage';
import SettingsPage from '@/pages/settings/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,        // 1 minute
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AdminAuthProvider>
          <Routes>
            {/* Public — Login */}
            <Route path="/admin/login" element={<LoginPage />} />

            {/* Protected — Admin shell */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AdminLayout />}>
                <Route path="/admin" element={<DashboardPage />} />
                <Route path="/admin/members" element={<MembersPage />} />
                <Route path="/admin/members/:id" element={<MemberDetailPage />} />
                <Route path="/admin/plans" element={<PlansPage />} />
                <Route path="/admin/system" element={<SystemPage />} />
                <Route path="/admin/settings" element={<SettingsPage />} />
              </Route>
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </AdminAuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
