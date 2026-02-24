import { Platform } from 'react-native';

// Auto-detect the right backend URL based on platform
const getBaseUrl = () => {
  if (Platform.OS === 'android') return 'http://10.0.2.2:8000'; // Android emulator -> host
  if (Platform.OS === 'web') return 'http://localhost:8000';     // Web browser
  return 'http://localhost:8000';                                 // iOS simulator
};

export const API_BASE = getBaseUrl();
