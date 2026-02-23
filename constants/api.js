import { Platform } from 'react-native';

// Change this to your computer's local IP when testing on a physical device
const LOCAL_IP = '192.168.1.188';

export const API_URL = Platform.OS === 'web'
  ? 'http://localhost:8000'
  : `http://${LOCAL_IP}:8000`;
