import { Platform } from 'react-native';
import Constants from 'expo-constants';

// ── API Configuration ──────────────────────────────────────────
// Priority:
//   1. EXPO_PUBLIC_API_URL env var (production / tunnel / staging)
//   2. Auto-detect from Expo dev server host (works on device + emulator)
//   3. Dev fallback — ping both known IPs (home + office)
//   4. Production — insurancenyou.com

// Your two dev machines / locations
const DEV_IPS = ['192.168.1.188', '192.168.1.50'];
const DEV_PORT = 8000;

const getApiUrl = () => {
  // 1. Explicit env var — set in .env or eas.json for builds
  const envUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envUrl) return envUrl;

  // 2. Auto-detect from Expo dev server (no hardcoded IP needed)
  if (__DEV__) {
    const debuggerHost =
      Constants.expoConfig?.hostUri ||
      Constants.manifest2?.extra?.expoGo?.debuggerHost ||
      Constants.manifest?.debuggerHost;
    if (debuggerHost) {
      const host = debuggerHost.split(':')[0]; // strip Expo's port
      return `http://${host}:${DEV_PORT}`;
    }
  }

  // 3. Production — your domain
  return 'https://api.insurancenyou.com';
};

// Probe known dev IPs — whichever responds first wins
let _resolvedDevUrl = null;
async function probeDevBackend() {
  if (_resolvedDevUrl) return _resolvedDevUrl;
  const raceProbes = DEV_IPS.map((ip) => {
    const url = `http://${ip}:${DEV_PORT}`;
    return fetch(`${url}/health`, { method: 'GET' })
      .then((r) => (r.ok ? url : Promise.reject()))
      .catch(() => Promise.reject());
  });
  try {
    _resolvedDevUrl = await Promise.any(raceProbes);
    console.log(`[API] Dev backend found at ${_resolvedDevUrl}`);
    return _resolvedDevUrl;
  } catch {
    return null; // neither responded
  }
}

export let API_URL = getApiUrl();

// On startup in dev, probe both IPs — if one answers, switch to it
if (__DEV__) {
  probeDevBackend().then((url) => {
    if (url) API_URL = url;
  });
}

// ── Fetch with timeout ─────────────────────────────────────────
// Default 15s timeout — all API calls should use this instead of raw fetch
export function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() =>
    clearTimeout(id)
  );
}
