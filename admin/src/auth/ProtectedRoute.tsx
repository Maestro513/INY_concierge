import { Navigate, Outlet } from 'react-router-dom';
import { useAdminAuth } from './AdminAuthProvider';
import { Skeleton } from '@/components/ui/skeleton';

export default function ProtectedRoute() {
  const { user, loading } = useAdminAuth();

  // DEV bypass — remove when backend auth is wired up
  if (import.meta.env.DEV) {
    return <Outlet />;
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="space-y-4 w-64">
          <Skeleton className="h-8 w-48 mx-auto" />
          <Skeleton className="h-4 w-32 mx-auto" />
          <Skeleton className="h-2 w-full" />
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/admin/login" replace />;
  }

  return <Outlet />;
}
