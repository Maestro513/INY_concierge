export const API_BASE = import.meta.env.VITE_API_URL || 'https://iny-concierge.onrender.com';

export const ENDPOINTS = {
  // Admin auth
  LOGIN: '/api/admin/auth/login',
  REFRESH: '/api/admin/auth/refresh',
  LOGOUT: '/api/admin/auth/logout',
  ME: '/api/admin/auth/me',

  // Members
  MEMBERS: '/api/admin/members',
  MEMBER: (phone: string) => `/api/admin/members/${phone}`,
  MEMBER_ACTIVITY: (phone: string) => `/api/admin/members/${phone}/activity`,
  MEMBER_CREATE: '/api/admin/members/create',
  MEMBER_SEND_OTP: '/api/admin/members/send-otp',
  MEMBER_REMINDERS: (phone: string) => `/api/admin/members/${phone}/reminders`,
  MEMBER_REMINDER: (phone: string, id: number) => `/api/admin/members/${phone}/reminders/${id}`,

  // Admin users (self-management)
  ADMIN_USERS: '/api/admin/users',
  ADMIN_USER: (id: number) => `/api/admin/users/${id}`,

  // Plans
  PLANS: '/api/admin/plans',
  PLAN: (id: string) => `/api/admin/plans/${id}`,

  // Extractions
  EXTRACTIONS_STATS: '/api/admin/extractions/stats',
  EXTRACTIONS_LIST: '/api/admin/extractions/list',

  // System
  HEALTH: '/api/admin/system/health',
  METRICS: '/api/admin/system/metrics',
  SESSIONS: '/api/admin/system/sessions',

  // Analytics
  ANALYTICS_LOGINS: '/api/admin/analytics/logins',
  ANALYTICS_ENROLLMENTS: '/api/admin/analytics/enrollments',
  ANALYTICS_FEATURES: '/api/admin/analytics/features',
  ANALYTICS_CARRIERS: '/api/admin/analytics/carriers',
  ANALYTICS_STATES: '/api/admin/analytics/states',
  ANALYTICS_AGE_GROUPS: '/api/admin/analytics/age-groups',
  // Screening & SDOH phone intake
  MEMBER_HEALTH_SCREENING: (phone: string) => `/api/admin/members/${phone}/health-screening`,
  MEMBER_SDOH_SCREENING: (phone: string) => `/api/admin/members/${phone}/sdoh-screening`,

  // Notifications
  MEMBER_NOTIFICATIONS: (phone: string) => `/api/admin/members/${phone}/notifications`,

  // Screening / SDOH history
  MEMBER_SCREENING_HISTORY: (phone: string) => `/api/admin/members/${phone}/screening-history`,

  // Utilization alerts
  MEMBER_UTILIZATION_ALERTS: (phone: string) => `/api/admin/members/${phone}/utilization-alerts`,

  // Secure messaging
  MEMBER_MESSAGES: (phone: string) => `/api/admin/members/${phone}/messages`,
  MESSAGES_INBOX: '/api/admin/messages/inbox',
} as const;
