import axios from 'axios';
import { API_BASE, ENDPOINTS } from '@/config/api';

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach admin token to every request
client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('admin_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Track whether a refresh is already in flight to avoid races
let _refreshPromise: Promise<boolean> | null = null;

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = sessionStorage.getItem('admin_refresh');
  if (!refreshToken) return false;
  try {
    const res = await axios.post(
      `${API_BASE}${ENDPOINTS.REFRESH}`,
      {},
      { headers: { Authorization: `Bearer ${refreshToken}` } },
    );
    const { access_token, refresh_token } = res.data;
    sessionStorage.setItem('admin_token', access_token);
    if (refresh_token) sessionStorage.setItem('admin_refresh', refresh_token);
    return true;
  } catch {
    return false;
  }
}

// Handle 401 → attempt token refresh, then retry or redirect to login
client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;

      // Coalesce concurrent refresh attempts
      if (!_refreshPromise) {
        _refreshPromise = _tryRefresh().finally(() => { _refreshPromise = null; });
      }
      const refreshed = await _refreshPromise;

      if (refreshed) {
        // Retry with new token
        original.headers.Authorization = `Bearer ${sessionStorage.getItem('admin_token')}`;
        return client(original);
      }

      // Refresh failed — clear and redirect
      sessionStorage.removeItem('admin_token');
      sessionStorage.removeItem('admin_refresh');
      window.location.href = '/admin/login';
    }
    return Promise.reject(err);
  }
);

export default client;
