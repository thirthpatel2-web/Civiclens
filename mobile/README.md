# CivicLens mobile (React Native + Expo, TypeScript)

Citizen client for the CivicLens FastAPI backend. **No business logic lives here and there is no Node backend.**

## Run
```bash
cd mobile
npm install
npx expo install --fix          # aligns package versions with your Expo SDK (versions in package.json were not resolved offline)
cp .env.example .env            # EXPO_PUBLIC_API_URL=http://10.0.2.2:8080 (Android emulator) | http://localhost:8080 (iOS sim) | https://your-server
npx expo start                  # Expo Go is enough for most features; a development build is needed for push tokens/background tasks
npm test                        # 30 Node tests over the pure TypeScript logic (client, offline sync, voice machine, strings)
npm run typecheck               # tsc against real types (after npm install);  sh tools/stubcheck.sh works without node_modules
```
Production builds must use an **HTTPS** API URL (the login screen warns otherwise). Android maps need a Google Maps API key in `app.json` (`android.config.googleMaps.apiKey`) — not supplied.

## Structure
`app/` expo-router screens: `(auth)/login|register`, `(tabs)/home|report|track|copilot|more`, `complaint/[id]`, `notifications`, `rti`, `legal`, `emergency`, `map`, `settings` ·
`src/api` typed client + endpoints + types (see `../docs/API_CONTRACT.md`) · `src/auth` secure-store session · `src/voice` state machine · `src/offline` draft store + sync engine + background task ·
`src/i18n` language registry + the shared dictionaries (byte-identical to the backend's; a test enforces it) · `src/components`, `src/hooks` · `tests/` · `legacy-prototype/` (earlier JS prototype, reference only).

## Voice
Press 🎤 → choose the spoken language (or **Auto-detect**, offered only if the server's engine supports it) → speak → the text appears **in the language you spoke, in its script**, editable, with the detected language and any warnings.
Nothing is translated. Offline, the recording is kept and transcribed later, then held for your review.

## Permissions (each is requested at the moment of use, with an explanation)
Microphone (voice input), camera / photos (evidence), location (only when you tap "Use my location"), notifications (after an explanatory card).

## Known limits
Never run on a device/emulator by the author. Push notifications need an EAS project id and `EXPO_PUSH_ENABLED=true` on the server; without them alerts work while the app is open (polling). Not ported from the legacy prototype: document scanner,
locator, department directory, official portal; no mobile screens yet for password reset, 2-factor enrolment or adding evidence to an existing complaint (the API supports all three).
