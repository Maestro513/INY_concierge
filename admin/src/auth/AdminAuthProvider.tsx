import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';
import type { AdminUser } from '@/types';

interface AuthState {
  user: AdminUser | null;
  loading: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });

  // Validate session on mount via /me (cookie sent automatically)
  useEffect(() => {
    client
      .get(ENDPOINTS.ME)
      .then((res) => {
        setState({ user: res.data, loading: false });
      })
      .catch(() => {
        setState({ user: null, loading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await client.post(ENDPOINTS.LOGIN, { email, password });
    setState({ user: res.data.user, loading: false });
  }, []);

  const logout = useCallback(async () => {
    try {
      await client.post(ENDPOINTS.LOGOUT);
    } catch {
      // Clear state even if logout request fails
    }
    setState({ user: null, loading: false });
  }, []);

  // Idle timeout — auto-logout after 30 minutes of inactivity
  useEffect(() => {
    if (!state.user) return;
    let timer: ReturnType<typeof setTimeout>;
    const resetTimer = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        logout();
      }, IDLE_TIMEOUT_MS);
    };
    const events = ['mousedown', 'keydown', 'scroll', 'touchstart'] as const;
    events.forEach((e) => window.addEventListener(e, resetTimer));
    resetTimer();
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, resetTimer));
    };
  }, [state.user, logout]);

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
