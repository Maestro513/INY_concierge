import { Platform } from 'react-native';

let AsyncStorage = null;
try {
  AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {
  console.log('[API] AsyncStorage native module not available. Token persistence disabled.');
}

// ── API Configuration ──────────────────────────────────────────
// Always uses Render backend. Set EXPO_PUBLIC_API_URL to override (e.g. for local dev).
const PROD_URL = 'https://iny-concierge.onrender.com';

const getApiUrl = () => {
  const envUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envUrl) return envUrl;
  return PROD_URL;
};

export let API_URL = getApiUrl();

// ── Token Storage ─────────────────────────────────────────────
const TOKEN_KEY = '@iny_access_token';
const REFRESH_KEY = '@iny_refresh_token';

let _accessToken = null;
let _refreshToken = null;

export async function setTokens(access, refresh) {
  _accessToken = access;
  _refreshToken = refresh;
  if (AsyncStorage) {
    await AsyncStorage.multiSet([
      [TOKEN_KEY, access],
      [REFRESH_KEY, refresh],
    ]);
  }
}

export async function loadTokens() {
  if (!AsyncStorage) return { access: null, refresh: null };
  try {
    const [[, access], [, refresh]] = await AsyncStorage.multiGet([TOKEN_KEY, REFRESH_KEY]);
    _accessToken = access;
    _refreshToken = refresh;
    return { access, refresh };
  } catch {
    return { access: null, refresh: null };
  }
}

export async function clearTokens() {
  _accessToken = null;
  _refreshToken = null;
  if (AsyncStorage) {
    await AsyncStorage.multiRemove([TOKEN_KEY, REFRESH_KEY]);
  }
}

export function getAccessToken() {
  return _accessToken;
}

// ── Authenticated Fetch ───────────────────────────────────────
// Wraps fetch with: timeout, Bearer token, auto-refresh on 401
export async function authFetch(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  const headers = { ...options.headers };
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`;
  }

  try {
    let res = await fetch(url, { ...options, headers, signal: controller.signal });

    // If 401 and we have a refresh token, try to refresh
    if (res.status === 401 && _refreshToken) {
      const refreshed = await _tryRefresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${_accessToken}`;
        // Retry with new token
        const controller2 = new AbortController();
        const id2 = setTimeout(() => controller2.abort(), timeoutMs);
        res = await fetch(url, { ...options, headers, signal: controller2.signal });
        clearTimeout(id2);
      }
    }

    return res;
  } finally {
    clearTimeout(id);
  }
}

async function _tryRefresh() {
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: _refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    await setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── Legacy: plain fetch with timeout (for pre-auth calls) ─────
export function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() =>
    clearTimeout(id)
  );
}
