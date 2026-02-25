import { Platform } from 'react-native';

// ── API Configuration ──────────────────────────────────────────
// For local dev:  leave TUNNEL_URL empty, set LOCAL_IP to your machine
// For demo/share: paste your cloudflare tunnel URL into TUNNEL_URL
const TUNNEL_URL = '';  // leave empty for local dev
const LOCAL_IP = '192.168.1.50';

export const API_URL = TUNNEL_URL
  || (Platform.OS === 'web' ? 'http://localhost:8000' : `http://${LOCAL_IP}:8000`);
