import { Platform } from 'react-native';

// Prefer expo-secure-store (encrypted keychain/keystore) for token storage.
// Falls back to encrypted AsyncStorage via secureCache on web or if SecureStore is unavailable.
let SecureStore = null;
let _secureCache = null;
try {
  SecureStore = require('expo-secure-store');
} catch (e) {
  // SecureStore not available (web or missing native module)
}
if (!SecureStore) {
  try {
    _secureCache = require('../utils/secureCache');
  } catch (e) {
    if (__DEV__) console.log('[API] No secure storage available. Token persistence disabled.');
  }
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
  if (SecureStore) {
    await SecureStore.setItemAsync(TOKEN_KEY, access);
    await SecureStore.setItemAsync(REFRESH_KEY, refresh);
  } else if (_secureCache) {
    await _secureCache.secureSet(TOKEN_KEY, access);
    await _secureCache.secureSet(REFRESH_KEY, refresh);
  }
}

export async function loadTokens() {
  try {
    let access, refresh;
    if (SecureStore) {
      access = await SecureStore.getItemAsync(TOKEN_KEY);
      refresh = await SecureStore.getItemAsync(REFRESH_KEY);
    } else if (_secureCache) {
      access = await _secureCache.secureGet(TOKEN_KEY);
      refresh = await _secureCache.secureGet(REFRESH_KEY);
    } else {
      return { access: null, refresh: null };
    }
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
  if (SecureStore) {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(REFRESH_KEY);
  } else if (_secureCache) {
    await _secureCache.secureRemove(TOKEN_KEY);
    await _secureCache.secureRemove(REFRESH_KEY);
  }
}

export function getAccessToken() {
  return _accessToken;
}

// ── Request ID generator ─────────────────────────────────────
function _generateRequestId() {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${ts}-${rand}`;
}

// ── Authenticated Fetch ───────────────────────────────────────
// Wraps fetch with: timeout, Bearer token, auto-refresh on 401, X-Request-ID
export async function authFetch(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  const headers = { ...options.headers };
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`;
  }
  if (!headers['X-Request-ID']) {
    headers['X-Request-ID'] = _generateRequestId();
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
export function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() =>
    clearTimeout(id)
  );
}
