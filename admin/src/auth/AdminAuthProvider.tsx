import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';
import type { AdminUser } from '@/types';

interface AuthState {
  user: AdminUser | null;
  token: string | null;
  loading: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token = localStorage.getItem('admin_token');
    return { user: null, token, loading: !!token };
  });

  // Fetch the current user profile on mount (if token exists)
  useEffect(() => {
    const token = localStorage.getItem('admin_token');
    if (!token) return;

    client
      .get(ENDPOINTS.ME)
      .then((res) => {
        setState({ user: res.data, token, loading: false });
      })
      .catch(() => {
        // Token invalid / expired
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_refresh');
        setState({ user: null, token: null, loading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await client.post(ENDPOINTS.LOGIN, { email, password });
    const { access_token, refresh_token, user } = res.data;
    localStorage.setItem('admin_token', access_token);
    if (refresh_token) localStorage.setItem('admin_refresh', refresh_token);
    setState({ user, token: access_token, loading: false });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_refresh');
    setState({ user: null, token: null, loading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdminAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAdminAuth must be used inside AdminAuthProvider');
  return ctx;
}
