/**
 * Encrypted cache layer for PHI data in AsyncStorage.
 *
 * AsyncStorage is plaintext on-device. This module encrypts values
 * using a random key stored in expo-secure-store (OS keychain/keystore).
 *
 * Strategy:
 *   1. On first use, generate a 256-bit random key via CSPRNG → store in SecureStore
 *   2. Encrypt JSON payloads with AES-GCM before writing to AsyncStorage
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
let _rawKey = null; // CryptoKey for AES-GCM

/**
 * Generate cryptographically secure random bytes.
 */
function _getRandomBytes(n) {
  const buf = new Uint8Array(n);
  if (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.getRandomValues) {
    globalThis.crypto.getRandomValues(buf);
  } else {
    // Should not happen on modern RN/Hermes — fail loudly rather than fall back to Math.random
    throw new Error('CSPRNG unavailable — cannot generate secure encryption key');
  }
  return buf;
}

function _bytesToHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function _hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

/**
 * Get or create the AES-GCM key from SecureStore.
 */
async function _getKey() {
  if (_rawKey) return _rawKey;
  if (!SecureStore) return null;
  try {
    let hexKey = await SecureStore.getItemAsync(CACHE_KEY_ID);
    if (!hexKey) {
      // Generate 256-bit key using CSPRNG
      const keyBytes = _getRandomBytes(32);
      hexKey = _bytesToHex(keyBytes);
      await SecureStore.setItemAsync(CACHE_KEY_ID, hexKey);
    }
    // Import as CryptoKey for AES-GCM if SubtleCrypto is available
    if (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.subtle) {
      _rawKey = await globalThis.crypto.subtle.importKey(
        'raw',
        _hexToBytes(hexKey),
        { name: 'AES-GCM' },
        false,
        ['encrypt', 'decrypt'],
      );
    } else {
      // Store raw hex for fallback path
      _rawKey = hexKey;
    }
    return _rawKey;
  } catch (e) {
    return null;
  }
}

/**
 * Check if we have SubtleCrypto AES-GCM support.
 */
function _hasSubtleCrypto() {
  return typeof globalThis.crypto !== 'undefined' && !!globalThis.crypto.subtle;
}

/**
 * AES-256-GCM encrypt. Returns base64 string of (IV || ciphertext || tag).
 */
async function _aesEncrypt(plaintext, cryptoKey) {
  const iv = _getRandomBytes(12); // 96-bit IV for GCM
  const encoded = new TextEncoder().encode(plaintext);
  const cipherBuf = await globalThis.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    encoded,
  );
  // Concatenate IV + ciphertext (tag is appended by WebCrypto)
  const combined = new Uint8Array(iv.length + cipherBuf.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipherBuf), iv.length);
  return _bytesToBase64(combined);
}

/**
 * AES-256-GCM decrypt. Input is base64 of (IV || ciphertext || tag).
 */
async function _aesDecrypt(b64, cryptoKey) {
  const combined = _base64ToBytes(b64);
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const plainBuf = await globalThis.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    ciphertext,
  );
  return new TextDecoder().decode(plainBuf);
}

function _bytesToBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function _base64ToBytes(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Encrypt and store a value in AsyncStorage.
 */
export async function secureSet(storageKey, value) {
  if (!AsyncStorage) return;
  const key = await _getKey();
  const json = JSON.stringify(value);
  if (key && _hasSubtleCrypto()) {
    const encrypted = await _aesEncrypt(json, key);
    await AsyncStorage.setItem(storageKey, 'aes:' + encrypted);
  } else if (key) {
    // Fallback: store with hex-key-based XOR (legacy, will be upgraded on next read+write)
    const encrypted = _bytesToBase64(
      new TextEncoder().encode(json).map((b, i) => b ^ _hexToBytes(key)[i % 32]),
    );
    await AsyncStorage.setItem(storageKey, 'enc:' + encrypted);
  } else {
    // No SecureStore available (web), store as-is
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
    if (raw.startsWith('aes:')) {
      const key = await _getKey();
      if (!key || !_hasSubtleCrypto()) return null;
      const decrypted = await _aesDecrypt(raw.slice(4), key);
      return JSON.parse(decrypted);
    }
    if (raw.startsWith('enc:')) {
      // Legacy XOR-encrypted data — decrypt, then re-encrypt with AES on next write
      const key = await _getKey();
      if (!key) return null;
      const hexKey = typeof key === 'string' ? key : null;
      if (!hexKey) return null;
      const cipherBytes = _base64ToBytes(raw.slice(4));
      const keyBytes = _hexToBytes(hexKey);
      const plainBytes = cipherBytes.map((b, i) => b ^ keyBytes[i % keyBytes.length]);
      const decrypted = new TextDecoder().decode(plainBytes);
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
  _rawKey = null;
  if (SecureStore) {
    try {
      await SecureStore.deleteItemAsync(CACHE_KEY_ID);
    } catch (e) {}
  }
}
