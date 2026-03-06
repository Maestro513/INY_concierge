import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Text } from 'react-native';
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
} from '@expo-google-fonts/inter';
import * as Sentry from '@sentry/react-native';
import { COLORS } from '../constants/theme';
import { setupNotificationChannel } from '../utils/notifications';

// ── Sentry error monitoring ─────────────────────────────────────
const SENTRY_DSN =
  process.env.EXPO_PUBLIC_SENTRY_DSN ||
  'https://d9858cf436e68998a5d2b4a31a8c7262@o4510966668132352.ingest.us.sentry.io/4510966737207297';

Sentry.init({
  dsn: SENTRY_DSN,
  environment: __DEV__ ? 'development' : 'production',
  tracesSampleRate: __DEV__ ? 1.0 : 0.2,
  beforeSend(event) {
    // Strip phone numbers from breadcrumbs
    if (event.breadcrumbs) {
      event.breadcrumbs = event.breadcrumbs.map((b) => {
        if (b.message) {
          b.message = b.message.replace(/\b\d{10}\b/g, '***PHONE***');
        }
        return b;
      });
    }
    return event;
  },
});

// expo-notifications requires a dev build (not available in Expo Go).
// Notification handler is set up in utils/notifications.js when reminders are created.

// Set Inter as default font for ALL Text and TextInput components app-wide
const originalTextRender = Text.render;
Text.render = function (...args) {
  const origin = originalTextRender.call(this, ...args);
  const style = origin.props.style || {};
  const flatStyle = Array.isArray(style)
    ? Object.assign({}, ...style.filter(Boolean))
    : typeof style === 'object'
      ? style
      : {};

  if (!flatStyle.fontFamily) {
    const weight = flatStyle.fontWeight;
    let family = 'Inter_400Regular';
    if (weight === '700' || weight === 'bold') family = 'Inter_700Bold';
    else if (weight === '600') family = 'Inter_600SemiBold';
    else if (weight === '500') family = 'Inter_500Medium';

    return {
      ...origin,
      props: {
        ...origin.props,
        style: [style, { fontFamily: family }],
      },
    };
  }
  return origin;
};

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
  });

  // Set up Android notification channel on app launch
  useEffect(() => {
    setupNotificationChannel();
  }, []);

  if (!fontsLoaded) return null;

  return (
    <Sentry.ErrorBoundary fallback={<Text style={{ padding: 40, textAlign: 'center' }}>Something went wrong. Please restart the app.</Text>}>
      <SafeAreaProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: COLORS.bg },
            animation: 'fade',
          }}
        >
          <Stack.Screen name="index" options={{ animation: 'none' }} />
          <Stack.Screen name="home" options={{ animation: 'fade', gestureEnabled: false }} />
          <Stack.Screen name="otp" options={{ animation: 'slide_from_right' }} />
          <Stack.Screen
            name="doctor-results"
            options={{ animation: 'slide_from_right', gestureEnabled: true }}
          />
          <Stack.Screen
            name="digital-id"
            options={{ animation: 'slide_from_right', gestureEnabled: true }}
          />
          <Stack.Screen
            name="pharmacy-results"
            options={{ animation: 'slide_from_right', gestureEnabled: true }}
          />
        </Stack>
      </SafeAreaProvider>
    </Sentry.ErrorBoundary>
  );
}
