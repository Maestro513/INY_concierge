/**
 * Notification utilities for medication reminders.
 *
 * Uses LOCAL scheduled notifications (not server push) so they
 * work offline and don't require push token infrastructure.
 *
 * NOTE: expo-notifications requires a dev build. In Expo Go the native
 * module isn't available, so all notification functions gracefully no-op.
 * Reminders still save to the backend — they just won't fire alerts
 * until you switch to a dev build.
 *
 * Flow:
 *   1. On login → fetchReminders() → syncAllReminders()
 *   2. On create/update → scheduleReminder() for the single item
 *   3. On delete → cancelReminder()
 */

// ── Lazy-load native modules (fail gracefully when not compiled in) ──
let AsyncStorageMod = null;
try {
  AsyncStorageMod = require('@react-native-async-storage/async-storage').default;
} catch (e) {
  console.log('[Notifications] AsyncStorage native module not available. Caching disabled.');
}

let Notifications = null;
try {
  Notifications = require('expo-notifications');
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
} catch (e) {
  console.log('[Notifications] Native module not available. Reminders will save but won\'t send alerts.');
}

// ── Android notification channel (required for Android 8+) ───────
export async function setupNotificationChannel() {
  if (!notifAvailable()) return;
  const { Platform } = require('react-native');
  if (Platform.OS === 'android') {
    try {
      await Notifications.setNotificationChannelAsync('medication-reminders', {
        name: 'Medication Reminders',
        importance: Notifications.AndroidImportance?.MAX ?? 4,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#7B3FBF',
        sound: 'default',
        description: 'Daily medication reminder alerts',
      });
    } catch (e) {
      console.log('[Notifications] Channel setup failed:', e.message);
    }
  }
}

function notifAvailable() {
  return Notifications !== null;
}

// ── Permission ──────────────────────────────────────────────────

export async function requestNotificationPermissions() {
  if (!notifAvailable()) return false;
  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    if (existing === 'granted') return true;
    const { status } = await Notifications.requestPermissionsAsync();
    return status === 'granted';
  } catch (e) {
    return false;
  }
}

export async function hasNotificationPermission() {
  if (!notifAvailable()) return false;
  try {
    const { status } = await Notifications.getPermissionsAsync();
    return status === 'granted';
  } catch (e) {
    return false;
  }
}

// ── Schedule / Cancel ───────────────────────────────────────────

export async function scheduleReminder(reminder) {
  if (!notifAvailable()) return;
  const notifId = `med-reminder-${reminder.id}`;

  try {
    await Notifications.cancelScheduledNotificationAsync(notifId).catch(() => {});
    if (!reminder.enabled) return;

    const doseText = reminder.dose_label ? ` (${reminder.dose_label})` : '';

    await Notifications.scheduleNotificationAsync({
      identifier: notifId,
      content: {
        title: '💊 Medication Reminder',
        body: `Time to take your ${reminder.drug_name}${doseText}`,
        sound: true,
        data: { type: 'med_reminder', reminder_id: reminder.id },
        categoryIdentifier: 'medication-reminders',
      },
      trigger: {
        type: 'daily',
        hour: reminder.time_hour,
        minute: reminder.time_minute,
        repeats: true,
        channelId: 'medication-reminders',
      },
    });
  } catch (e) {
    console.log('[Notifications] Schedule failed:', e.message);
  }
}

export async function cancelReminder(reminderId) {
  if (!notifAvailable()) return;
  try {
    await Notifications.cancelScheduledNotificationAsync(`med-reminder-${reminderId}`);
  } catch (e) {}
}

export async function syncAllReminders(reminders) {
  if (!notifAvailable()) return;
  try {
    const scheduled = await Notifications.getAllScheduledNotificationsAsync();
    for (const notif of scheduled) {
      if (notif.identifier.startsWith('med-reminder-')) {
        await Notifications.cancelScheduledNotificationAsync(notif.identifier);
      }
    }
    for (const r of reminders) {
      if (r.enabled) await scheduleReminder(r);
    }
  } catch (e) {
    console.log('[Notifications] Sync failed:', e.message);
  }
}

// ── AsyncStorage cache ──────────────────────────────────────────

const REMINDERS_CACHE_KEY = '@med_reminders';
const USAGE_CACHE_KEY = '@benefits_usage_summary';

export async function cacheReminders(reminders) {
  if (!AsyncStorageMod) return;
  try {
    await AsyncStorageMod.setItem(REMINDERS_CACHE_KEY, JSON.stringify(reminders));
  } catch (e) {}
}

export async function getCachedReminders() {
  if (!AsyncStorageMod) return null;
  try {
    const data = await AsyncStorageMod.getItem(REMINDERS_CACHE_KEY);
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
}

export async function cacheUsageSummary(summary) {
  if (!AsyncStorageMod) return;
  try {
    await AsyncStorageMod.setItem(USAGE_CACHE_KEY, JSON.stringify(summary));
  } catch (e) {}
}

export async function getCachedUsageSummary() {
  if (!AsyncStorageMod) return null;
  try {
    const data = await AsyncStorageMod.getItem(USAGE_CACHE_KEY);
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
}
