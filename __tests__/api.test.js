/**
 * Tests for the token management functions in constants/api.js.
 *
 * We mock expo-secure-store and verify set/load/clear token operations.
 */

// Mock react-native Platform before anything imports it
jest.mock('react-native', () => ({
  Platform: { OS: 'android', select: jest.fn((obj) => obj.android) },
}));

// Mock expo-secure-store with jest functions
const mockSecureStore = {
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  getItemAsync: jest.fn().mockResolvedValue(null),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
};
jest.mock('expo-secure-store', () => mockSecureStore);

const { setTokens, loadTokens, clearTokens, getAccessToken } = require('../constants/api');

describe('Token Management', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('setTokens stores tokens in SecureStore', async () => {
    await setTokens('access-123', 'refresh-456');
    expect(mockSecureStore.setItemAsync).toHaveBeenCalledWith('@iny_access_token', 'access-123');
    expect(mockSecureStore.setItemAsync).toHaveBeenCalledWith('@iny_refresh_token', 'refresh-456');
  });

  test('loadTokens retrieves tokens from SecureStore', async () => {
    mockSecureStore.getItemAsync
      .mockResolvedValueOnce('stored-access')
      .mockResolvedValueOnce('stored-refresh');
    const tokens = await loadTokens();
    expect(tokens.access).toBe('stored-access');
    expect(tokens.refresh).toBe('stored-refresh');
  });

  test('loadTokens handles missing tokens', async () => {
    mockSecureStore.getItemAsync.mockResolvedValueOnce(null).mockResolvedValueOnce(null);
    const tokens = await loadTokens();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });

  test('clearTokens removes tokens from SecureStore', async () => {
    await setTokens('access-123', 'refresh-456');
    await clearTokens();
    expect(mockSecureStore.deleteItemAsync).toHaveBeenCalledWith('@iny_access_token');
    expect(mockSecureStore.deleteItemAsync).toHaveBeenCalledWith('@iny_refresh_token');
    expect(getAccessToken()).toBeNull();
  });

  test('getAccessToken returns current in-memory token', async () => {
    await setTokens('my-token', 'my-refresh');
    expect(getAccessToken()).toBe('my-token');
  });
});
