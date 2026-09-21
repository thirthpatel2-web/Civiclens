// CivicLens - Voice Recording & Real-Time Speech-to-Text Recognition Service
//
// Web: real continuous Web Speech API + real getUserMedia volume analysis
// (the volume data actually drives the UI waveform — see
// VoiceListeningModal.js — instead of being computed and discarded).
//
// Native (iOS/Android): real on-device speech recognition via
// @react-native-voice/voice, which wraps Apple's Speech framework and
// Android's SpeechRecognizer. This is free forever, no API key, and never
// sends audio anywhere — but it's a native module, so it only works in a
// custom dev client / production build, NOT in Expo Go. If the module
// isn't linked (you're likely in Expo Go), this fails gracefully with a
// clear message instead of silently doing nothing, which is what the
// previous cloud-Whisper-less version did.
//
// An optional paid cloud alternative (supabase/functions/transcribe-audio)
// still exists in the repo for anyone who'd rather pay for Whisper than
// build a dev client — see transcribeAudioFile() below — but it is not
// used by the default flow.

import { Platform } from 'react-native';
import { apiRequest, isBackendConfigured } from './apiClient';

let activeWebRecognition = null;
let isUserListeningActive = false;
let webAudioContext = null;
let webMediaStream = null;
let nativeVoiceActive = false;

let VoiceModule = null;
function getVoiceModule() {
  if (VoiceModule !== null) return VoiceModule;
  try {
    // Lazily required so Expo Go (which has no native module for this)
    // doesn't crash on import — it just means the module stays `false`.
    VoiceModule = require('@react-native-voice/voice').default;
  } catch (e) {
    VoiceModule = false;
  }
  return VoiceModule;
}

// Map language codes to BCP 47 language tags for Speech Recognition
const BCP47_LANG_MAP = {
  en: 'en-IN',
  hi: 'hi-IN',
  kn: 'kn-IN',
  ta: 'ta-IN',
  te: 'te-IN',
  mr: 'mr-IN',
  bn: 'bn-IN',
};

// Start listening for speech with live continuous transcription, volume analysis & auto-reconnect
export const startLiveSpeechRecognition = async (language = 'en', onResult, onError, onVolumeChange) => {
  isUserListeningActive = true;

  // 1. Web Platform (Chrome, Edge, Safari, Android Web)
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    // Prompt for mic permission via getUserMedia
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        webMediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Setup live audio volume analyzer
        if (typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined') {
          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          webAudioContext = new AudioCtx();
          const source = webAudioContext.createMediaStreamSource(webMediaStream);
          const analyser = webAudioContext.createAnalyser();
          analyser.fftSize = 64;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          const checkVolume = () => {
            if (!isUserListeningActive) return;
            analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) {
              sum += dataArray[i];
            }
            const avg = sum / dataArray.length;
            if (onVolumeChange) {
              onVolumeChange(Math.min(100, Math.round((avg / 128) * 100)));
            }
            requestAnimationFrame(checkVolume);
          };
          requestAnimationFrame(checkVolume);
        }
      }
    } catch (micErr) {
      console.log('Mic permission notice:', micErr);
      if (onError) onError('Please allow microphone permissions in your browser address bar.');
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        if (activeWebRecognition) {
          try {
            activeWebRecognition.abort();
          } catch (e) {}
          activeWebRecognition = null;
        }

        const recognition = new SpeechRecognition();
        recognition.lang = BCP47_LANG_MAP[language] || 'en-IN';
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        let accumulatedFinal = '';

        recognition.onresult = (event) => {
          let currentInterim = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0]?.transcript || '';
            if (event.results[i].isFinal) {
              accumulatedFinal += (accumulatedFinal ? ' ' : '') + transcript.trim();
            } else {
              currentInterim += (currentInterim ? ' ' : '') + transcript.trim();
            }
          }

          const combinedText = (accumulatedFinal + (currentInterim ? ' ' + currentInterim : '')).trim();
          if (combinedText && onResult) {
            onResult(combinedText);
          }
        };

        recognition.onerror = (event) => {
          console.log('Web Speech API event notice:', event.error);
          if (event.error === 'not-allowed') {
            if (onError) onError('Microphone access is blocked. Please allow mic in browser address bar.');
          } else if (event.error !== 'no-speech' && onError) {
            onError(event.error);
          }
        };

        recognition.onend = () => {
          // Auto-restart if user has not explicitly stopped listening
          if (isUserListeningActive) {
            try {
              recognition.start();
            } catch (reErr) {
              // Ignore if already started
            }
          } else {
            activeWebRecognition = null;
          }
        };

        recognition.start();
        activeWebRecognition = recognition;
        return { success: true, isLive: true, mode: 'web_speech' };
      } catch (err) {
        console.log('Speech recognition initialization notice:', err);
      }
    }
  }

  // 2. Native on-device speech recognition (free forever, no API key, no
  //    network call — requires a custom dev client, not Expo Go).
  const Voice = getVoiceModule();
  if (!Voice) {
    const msg =
      'On-device speech recognition isn\'t linked in this build. Run "npx expo prebuild" and build a dev client (see README) — Expo Go can\'t run native voice recognition.';
    console.log(msg);
    if (onError) onError(msg);
    return { success: false, error: 'native_voice_unavailable', mode: 'unavailable' };
  }

  try {
    Voice.onSpeechResults = (e) => {
      const text = (e.value && e.value[0]) || '';
      if (text && onResult) onResult(text);
    };
    Voice.onSpeechPartialResults = (e) => {
      const text = (e.value && e.value[0]) || '';
      if (text && onResult) onResult(text);
    };
    Voice.onSpeechVolumeChanged = (e) => {
      // Android reports roughly 0-10; iOS varies. Normalize to 0-100 for
      // the shared waveform UI.
      if (onVolumeChange) {
        onVolumeChange(Math.min(100, Math.max(0, Math.round((e.value || 0) * 10))));
      }
    };
    Voice.onSpeechError = (e) => {
      console.log('Native speech recognition notice:', e.error);
      if (onError) onError(e.error?.message || 'Speech recognition error — you can also type your issue.');
    };

    await Voice.start(BCP47_LANG_MAP[language] || 'en-IN');
    nativeVoiceActive = true;
    return { success: true, isLive: true, mode: 'native_voice' };
  } catch (error) {
    console.log('Native voice recognition notice:', error.message);
    if (onError) onError(error.message);
    return { success: false, error: error.message };
  }
};

// Stop listening and finalize the transcript
export const stopLiveSpeechRecognition = async () => {
  isUserListeningActive = false;

  if (Platform.OS === 'web') {
    if (activeWebRecognition) {
      try {
        activeWebRecognition.stop();
      } catch (e) {}
      activeWebRecognition = null;
    }
    if (webMediaStream) {
      try {
        webMediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {}
      webMediaStream = null;
    }
    if (webAudioContext) {
      try {
        webAudioContext.close();
      } catch (e) {}
      webAudioContext = null;
    }
    return { success: true };
  }

  if (nativeVoiceActive) {
    const Voice = getVoiceModule();
    if (Voice) {
      try {
        await Voice.stop();
      } catch (e) {
        console.log('Error stopping native voice recognition:', e.message);
      }
    }
    nativeVoiceActive = false;
  }

  return { success: true };
};

export const cancelLiveSpeechRecognition = async () => {
  isUserListeningActive = false;
  if (activeWebRecognition) {
    try {
      activeWebRecognition.abort();
    } catch (e) {}
    activeWebRecognition = null;
  }
  if (webMediaStream) {
    try {
      webMediaStream.getTracks().forEach((track) => track.stop());
    } catch (e) {}
    webMediaStream = null;
  }
  if (webAudioContext) {
    try {
      webAudioContext.close();
    } catch (e) {}
    webAudioContext = null;
  }
  if (nativeVoiceActive) {
    const Voice = getVoiceModule();
    if (Voice) {
      try {
        await Voice.cancel();
      } catch (e) {}
    }
    nativeVoiceActive = false;
  }
  return { success: true };
};

export const isLiveSpeechSupported = () => {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }
  return !!getVoiceModule();
};

/**
 * OPTIONAL paid alternative — not used by the default on-device flow above.
 * Sends a recorded audio file to a real Whisper API call via the
 * server's /voice/transcribe route. Kept for anyone who'd rather pay
 * per-minute for cloud transcription than build a dev client for the free
 * on-device path. Requires OPENAI_API_KEY set on the server — see
 * server/.env.example.
 */
export const transcribeAudioFile = async (audioUri, language = 'en') => {
  if (!audioUri) return { success: false, error: 'No recording to transcribe.' };
  if (!isBackendConfigured) {
    return {
      success: false,
      error: 'Cloud transcription is not connected, and this is an optional paid path anyway — the on-device recognizer above is the free default.',
    };
  }
  try {
    const FileSystem = require('expo-file-system');
    const base64 = await FileSystem.readAsStringAsync(audioUri, { encoding: FileSystem.EncodingType.Base64 });
    const { data, error } = await apiRequest('/voice/transcribe', {
      method: 'POST',
      body: { audioBase64: base64, language, mimeType: 'audio/m4a' },
    });
    if (error || !data?.success) {
      return { success: false, error: error || 'Transcription failed.' };
    }
    return { success: true, transcript: data.transcript };
  } catch (e) {
    return { success: false, error: e.message };
  }
};
