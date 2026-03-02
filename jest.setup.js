// Mock AsyncStorage — the source code uses require('...').default,
// so we need both named exports and a .default that points to the same mock.
jest.mock('@react-native-async-storage/async-storage', () => {
  const mock = {
    setItem: jest.fn(() => Promise.resolve()),
    getItem: jest.fn(() => Promise.resolve(null)),
    removeItem: jest.fn(() => Promise.resolve()),
    multiSet: jest.fn(() => Promise.resolve()),
    multiGet: jest.fn(() =>
      Promise.resolve([
        ['@iny_access_token', null],
        ['@iny_refresh_token', null],
      ]),
    ),
    multiRemove: jest.fn(() => Promise.resolve()),
  };
  mock.default = mock;
  return mock;
});

// Mock expo modules that aren't available in test environment
jest.mock('expo-speech-recognition', () => ({}));
jest.mock('expo-speech', () => ({ speak: jest.fn(), stop: jest.fn() }));
jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn(() => Promise.resolve({ status: 'granted' })),
  requestPermissionsAsync: jest.fn(() => Promise.resolve({ status: 'granted' })),
  scheduleNotificationAsync: jest.fn(() => Promise.resolve('notif-id')),
  cancelAllScheduledNotificationsAsync: jest.fn(() => Promise.resolve()),
}));
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useLocalSearchParams: () => ({}),
  Stack: { Screen: 'Screen' },
}));

// Silence console.log in tests
global.console = {
  ...console,
  log: jest.fn(),
  debug: jest.fn(),
  info: jest.fn(),
};
