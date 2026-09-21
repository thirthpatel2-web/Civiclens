// CivicLens - Email Dispatch Service (custom backend)
// Tries a real, automatic, server-side send first (via server/src/routes/email.js
// -> Resend). Falls back to mailto: if not configured or the call fails.

import { Linking } from 'react-native';
import { apiRequest, isBackendConfigured } from './apiClient';

function openMailtoFallback({ to, subject, body }) {
  const mailUrl = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  Linking.openURL(mailUrl);
  return { success: true, method: 'mailto', sentAutomatically: false };
}

export async function sendEmail({ to, subject, body, attachmentBase64, attachmentFilename }) {
  if (isBackendConfigured) {
    const { data, error } = await apiRequest('/email/send', {
      method: 'POST',
      body: { to, subject, body, attachmentBase64, attachmentFilename },
    });
    if (!error && data?.success) {
      return { success: true, method: 'resend', sentAutomatically: true };
    }
    console.log('Real email send failed, falling back to mailto:', error);
  }
  return openMailtoFallback({ to, subject, body });
}
