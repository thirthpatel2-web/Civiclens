// CivicLens - On-Device Text Extraction (100% free, no API key, no cloud call)
//
// Web: Tesseract.js runs OCR entirely in the browser via WebAssembly.
// Native (iOS/Android): Google ML Kit's on-device text recognizer runs
// locally on the phone. Neither sends the image anywhere or costs anything,
// ever — but both require native code, which means this only works in a
// custom dev client / production build, NOT in Expo Go. See README for the
// `npx expo prebuild` + `eas build` (or `expo run:android`/`run:ios`) setup.
//
// If you're still running in Expo Go, these calls will fail gracefully and
// the app falls back to manual document-category selection — it won't crash,
// but on-device OCR genuinely cannot run until you build a dev client.

import { Platform } from 'react-native';

let mlKitTextRecognitionModule = null;
function getMlKitModule() {
  if (mlKitTextRecognitionModule !== null) return mlKitTextRecognitionModule;
  try {
    // Required lazily so Expo Go (which has no native module for this)
    // doesn't crash on import — it just means the module stays null and
    // extractTextFromImage() reports it's unavailable.
    mlKitTextRecognitionModule = require('@react-native-ml-kit/text-recognition').default;
  } catch (e) {
    mlKitTextRecognitionModule = false;
  }
  return mlKitTextRecognitionModule;
}

/**
 * Extracts real text from a photo entirely on-device — free, no API key,
 * no network call. Returns { success, text, available } — `available:
 * false` means the native module isn't linked yet (you're likely running
 * in Expo Go instead of a custom dev client).
 */
export async function extractTextFromImage(imageUri) {
  if (Platform.OS === 'web') {
    try {
      const Tesseract = await import('tesseract.js');
      const { data } = await Tesseract.recognize(imageUri, 'eng');
      return { success: true, available: true, text: (data.text || '').trim(), confidence: data.confidence };
    } catch (e) {
      return { success: false, available: true, error: e.message, text: '' };
    }
  }

  const MlKit = getMlKitModule();
  if (!MlKit) {
    return {
      success: false,
      available: false,
      error: 'On-device text recognition isn\'t linked in this build. Run "npx expo prebuild" and build a dev client (see README) — Expo Go can\'t run native OCR.',
      text: '',
    };
  }

  try {
    const result = await MlKit.recognize(imageUri);
    return { success: true, available: true, text: (result?.text || '').trim(), confidence: null };
  } catch (e) {
    return { success: false, available: true, error: e.message, text: '' };
  }
}
