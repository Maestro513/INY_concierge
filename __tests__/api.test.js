/**
 * Tests for the token management functions in constants/api.js.
 *
 * We mock AsyncStorage and verify set/load/clear token operations.
 */

// Mock react-native Platform before anything imports it
jest.mock('react-native', () => ({
  Platform: { OS: 'android', select: jest.fn((obj) => obj.android) },
}));

const AsyncStorage = require('@react-native-async-storage/async-storage');
const { setTokens, loadTokens, clearTokens, getAccessToken } = require('../constants/api');

describe('Token Management', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('setTokens stores tokens in AsyncStorage', async () => {
    await setTokens('access-123', 'refresh-456');
    expect(AsyncStorage.multiSet).toHaveBeenCalledWith([
      ['@iny_access_token', 'access-123'],
      ['@iny_refresh_token', 'refresh-456'],
    ]);
  });

  test('loadTokens retrieves tokens from AsyncStorage', async () => {
    AsyncStorage.multiGet.mockResolvedValueOnce([
      ['@iny_access_token', 'stored-access'],
      ['@iny_refresh_token', 'stored-refresh'],
    ]);
    const tokens = await loadTokens();
    expect(tokens.access).toBe('stored-access');
    expect(tokens.refresh).toBe('stored-refresh');
  });

  test('loadTokens handles missing tokens', async () => {
    AsyncStorage.multiGet.mockResolvedValueOnce([
      ['@iny_access_token', null],
      ['@iny_refresh_token', null],
    ]);
    const tokens = await loadTokens();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });

  test('clearTokens removes tokens from AsyncStorage', async () => {
    await setTokens('access-123', 'refresh-456');
    await clearTokens();
    expect(AsyncStorage.multiRemove).toHaveBeenCalledWith([
      '@iny_access_token',
      '@iny_refresh_token',
    ]);
    expect(getAccessToken()).toBeNull();
  });

  test('getAccessToken returns current in-memory token', async () => {
    await setTokens('my-token', 'my-refresh');
    expect(getAccessToken()).toBe('my-token');
  });
});
