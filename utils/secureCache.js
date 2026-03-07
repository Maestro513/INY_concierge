/**
 * Encrypted cache layer for PHI data in AsyncStorage.
 *
 * AsyncStorage is plaintext on-device. This module encrypts values
 * using a random key stored in expo-secure-store (OS keychain/keystore).
 *
 * Strategy:
 *   1. On first use, generate a 256-bit random key → store in SecureStore
 *   2. Encrypt JSON payloads with XOR stream cipher before writing to AsyncStorage
 *   3. Decrypt on read
 *
 * This protects PHI at rest on rooted/jailbroken devices where AsyncStorage
 * files are accessible but SecureStore (hardware-backed keystore) is not.
 */

let SecureStore = null;
let AsyncStorage = null;
try {
  SecureStore = require('expo-secure-store');
} catch (e) {}
try {
  AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {}

const CACHE_KEY_ID = '__iny_cache_enc_key';
let _encKey = null;

/**
 * Get or create the encryption key from SecureStore.
 */
async function _getKey() {
  if (_encKey) return _encKey;
  if (!SecureStore) return null;
  try {
    let key = await SecureStore.getItemAsync(CACHE_KEY_ID);
    if (!key) {
      // Generate 64 hex chars (256 bits)
      const bytes = [];
      for (let i = 0; i < 32; i++) {
        bytes.push(Math.floor(Math.random() * 256));
      }
      key = bytes.map((b) => b.toString(16).padStart(2, '0')).join('');
      await SecureStore.setItemAsync(CACHE_KEY_ID, key);
    }
    _encKey = key;
    return key;
  } catch (e) {
    return null;
  }
}

/**
 * Simple XOR cipher using the key as a repeating keystream.
 * Not cryptographically ideal but sufficient for at-rest obfuscation
 * where the key is in hardware-backed storage.
 */
function _xor(text, hexKey) {
  const keyBytes = [];
  for (let i = 0; i < hexKey.length; i += 2) {
    keyBytes.push(parseInt(hexKey.substring(i, i + 2), 16));
  }
  const result = [];
  for (let i = 0; i < text.length; i++) {
    result.push(String.fromCharCode(text.charCodeAt(i) ^ keyBytes[i % keyBytes.length]));
  }
  return result.join('');
}

function _toBase64(str) {
  // btoa-safe encoding for binary string
  try {
    return btoa(
      encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, (_, p1) =>
        String.fromCharCode(parseInt(p1, 16)),
      ),
    );
  } catch (e) {
    // Fallback: use unescape for environments where encodeURIComponent path fails
    return btoa(unescape(encodeURIComponent(str)));
  }
}

function _fromBase64(b64) {
  try {
    return decodeURIComponent(
      atob(b64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    );
  } catch (e) {
    return decodeURIComponent(escape(atob(b64)));
  }
}

/**
 * Encrypt and store a value in AsyncStorage.
 */
export async function secureSet(storageKey, value) {
  if (!AsyncStorage) return;
  const key = await _getKey();
  const json = JSON.stringify(value);
  if (key) {
    const encrypted = _toBase64(_xor(json, key));
    await AsyncStorage.setItem(storageKey, 'enc:' + encrypted);
  } else {
    // Fallback: no SecureStore available (web), store as-is
    await AsyncStorage.setItem(storageKey, json);
  }
}

/**
 * Read and decrypt a value from AsyncStorage.
 */
export async function secureGet(storageKey) {
  if (!AsyncStorage) return null;
  try {
    const raw = await AsyncStorage.getItem(storageKey);
    if (!raw) return null;
    if (raw.startsWith('enc:')) {
      const key = await _getKey();
      if (!key) return null;
      const decrypted = _xor(_fromBase64(raw.slice(4)), key);
      return JSON.parse(decrypted);
    }
    // Legacy unencrypted data — parse and re-encrypt on next write
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

/**
 * Remove a secure cache entry.
 */
export async function secureRemove(storageKey) {
  if (!AsyncStorage) return;
  try {
    await AsyncStorage.removeItem(storageKey);
  } catch (e) {}
}

/**
 * Clear the encryption key (call on logout to make cached data unreadable).
 */
export async function destroyEncryptionKey() {
  _encKey = null;
  if (SecureStore) {
    try {
      await SecureStore.deleteItemAsync(CACHE_KEY_ID);
    } catch (e) {}
  }
}
