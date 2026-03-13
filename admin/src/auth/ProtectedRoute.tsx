import { Navigate, Outlet } from 'react-router-dom';
import { useAdminAuth } from './AdminAuthProvider';
import { Skeleton } from '@/components/ui/skeleton';

interface ProtectedRouteProps {
  /** Roles allowed to access this route. If omitted, any authenticated active user is allowed. */
  allowedRoles?: Array<'super_admin' | 'admin' | 'viewer'>;
}

export default function ProtectedRoute({ allowedRoles }: ProtectedRouteProps = {}) {
  const { user, loading } = useAdminAuth();

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

  if (!user || !user.is_active) {
    return <Navigate to="/admin/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/admin" replace />;
  }

  return <Outlet />;
}
