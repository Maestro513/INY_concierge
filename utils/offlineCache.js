/**
 * Offline-first cache layer for API responses.
 *
 * Strategy: network-first with AsyncStorage fallback.
 * - On success: cache response + serve fresh data
 * - On failure: serve cached data if available
 * - ETags are stored so the backend can return 304 Not Modified
 */

let AsyncStorage = null;
try {
  AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {
  // AsyncStorage not available (e.g. test environment)
}

const CACHE_PREFIX = '@iny_cache:';
const ETAG_PREFIX = '@iny_etag:';

/**
 * Get cached data for a URL.
 * @returns {{ data: any, etag: string|null } | null}
 */
export async function getCached(url) {
  if (!AsyncStorage) return null;
  try {
    const raw = await AsyncStorage.getItem(CACHE_PREFIX + url);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // Check TTL if set (optional, mainly for non-ETag endpoints)
    if (parsed.expiresAt && Date.now() > parsed.expiresAt) {
      return null;
    }
    const etag = await AsyncStorage.getItem(ETAG_PREFIX + url);
    return { data: parsed.data, etag };
  } catch {
    return null;
  }
}

/**
 * Store data + ETag for a URL.
 * @param {string} url
 * @param {any} data
 * @param {string|null} etag
 * @param {number} ttlMs - optional TTL in ms (default: 24 hours)
 */
export async function setCache(url, data, etag = null, ttlMs = 86400000) {
  if (!AsyncStorage) return;
  try {
    const entry = { data, expiresAt: Date.now() + ttlMs };
    const pairs = [[CACHE_PREFIX + url, JSON.stringify(entry)]];
    if (etag) {
      pairs.push([ETAG_PREFIX + url, etag]);
    }
    await AsyncStorage.multiSet(pairs);
  } catch {
    // Cache write failures are non-fatal
  }
}

/**
 * Network-first fetch with offline fallback.
 * Use for GET endpoints that support ETag caching.
 *
 * @param {Function} fetchFn - the fetch function (authFetch or fetchWithTimeout)
 * @param {string} url - full API URL
 * @param {object} options - fetch options
 * @param {number} timeoutMs
 * @returns {{ data: any, fromCache: boolean }}
 */
export async function cachedFetch(fetchFn, url, options = {}, timeoutMs = 15000) {
  const cached = await getCached(url);

  // Add If-None-Match header if we have a cached ETag
  const headers = { ...options.headers };
  if (cached?.etag) {
    headers['If-None-Match'] = cached.etag;
  }

  try {
    const res = await fetchFn(url, { ...options, headers }, timeoutMs);

    // 304 Not Modified — return cached data
    if (res.status === 304 && cached) {
      return { data: cached.data, fromCache: true };
    }

    if (!res.ok) {
      // Network error but we have cache — return it
      if (cached) return { data: cached.data, fromCache: true };
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    const etag = res.headers.get('ETag') || res.headers.get('etag');
    await setCache(url, data, etag);
    return { data, fromCache: false };
  } catch (err) {
    // Network failure — serve from cache if available
    if (cached) {
      return { data: cached.data, fromCache: true };
    }
    throw err;
  }
}

/**
 * Clear all cached data (e.g. on logout).
 */
export async function clearAllCache() {
  if (!AsyncStorage) return;
  try {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter(
      (k) => k.startsWith(CACHE_PREFIX) || k.startsWith(ETAG_PREFIX),
    );
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
    }
  } catch {
    // Non-fatal
  }
}
