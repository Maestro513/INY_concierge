import axios from 'axios';
import { API_BASE, ENDPOINTS } from '@/config/api';

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Track whether a refresh is already in flight to avoid races
let _refreshPromise: Promise<boolean> | null = null;

async function _tryRefresh(): Promise<boolean> {
  try {
    await axios.post(
      `${API_BASE}${ENDPOINTS.REFRESH}`,
      {},
      { withCredentials: true },
    );
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
        // Retry — cookies are updated automatically
        return client(original);
      }

      // Refresh failed — redirect to login
      window.location.href = '/admin/login';
    }
    return Promise.reject(err);
  }
);

export default client;
