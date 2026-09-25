# CivicLens (React Native + Expo, TypeScript)

The one CivicLens client app — citizen, officer, integration-admin and auditor all sign into the
same app, same codebase, and the server decides what they see. Runs on the **web** (any browser,
`npm run web`) and on **Android/iOS** (`npx expo start` + Expo Go, or a real device build) from
this single source tree — there is no separate "mobile" app and no separate "web" app to keep in
sync. **No business logic lives here and there is no Node backend**; every screen is a thin client
of the CivicLens FastAPI backend.

## Run
```bash
cd classic-app
npm install
npx expo install --fix          # aligns package versions with your Expo SDK (versions in package.json were not resolved offline)
cp .env.example .env            # EXPO_PUBLIC_API_URL=http://10.0.2.2:8080 (Android emulator) | http://localhost:8080 (iOS sim/web) | https://your-server
npm run web                     # opens in your browser at http://localhost:8081
npx expo start                  # scan the QR code with Expo Go on a phone instead
npm test                        # Node test runner over the pure TypeScript logic (client, offline sync, voice machine, strings)
npm run typecheck               # tsc against real types (after npm install); sh tools/stubcheck.sh works without node_modules
```
Production builds must use an **HTTPS** API URL (the login screen warns otherwise). Android maps need a Google Maps API key in `app.json` (`android.config.googleMaps.apiKey`) — not supplied.

## Structure
`app/` expo-router screens: `(auth)/login|register|landing`, `(tabs)/home|report|track|copilot|more`, `(officer)/*`, `complaint/[id]`, `officer-complaint/*`, `investigation/*`,
`notifications`, `legal` (case analyser / precedent search), `emergency`, `locator`, `directory`, `documents`, `map` (+ `map.web` for the browser), `monitoring`, `workflow-rules`,
`interop-gateway` (the cross-department integration console), `settings` — RTI filing lives inside `(tabs)/report` as a tab, not a separate screen ·
`src/api` typed client + endpoints + types (see `../docs/API_CONTRACT.md`) · `src/auth` secure-store session · `src/voice` state machine · `src/offline` draft store + sync engine + background task ·
`src/i18n` language registry + the shared dictionaries (byte-identical to the backend's; a test enforces it) · `src/components`, `src/hooks` · `tests/`.

## Voice
Press 🎤 → choose the spoken language (or **Auto-detect**, offered only if the server's engine supports it) → speak → the text appears **in the language you spoke, in its script**, editable, with the detected language and any warnings.
Nothing is translated. Offline, the recording is kept and transcribed later, then held for your review.

## Permissions (each is requested at the moment of use, with an explanation)
Microphone (voice input), camera / photos (evidence), location (only when you tap "Use my location"), notifications (after an explanatory card).

## Known limits
Push notifications need an EAS project id and `EXPO_PUSH_ENABLED=true` on the server; without them alerts work while the app is open (polling). Two-factor authentication is fully optional and
never blocks sign-in for any account (enroll it yourself from Settings if you want it on your own account) - it does not gate login the way it used to.

## Building for app stores
`eas.json` has `development`/`preview`/`production` profiles scaffolded, but two things need real values before a build is usable, neither of which can be filled in without your accounts:
1. Run `eas login` then `eas init` (needs an Expo account) - this writes a real `extra.eas.projectId` into `app.json`.
2. Replace the placeholder `EXPO_PUBLIC_API_URL` values in `eas.json` (`https://staging.example.org`, `https://api.example.org`) with your actual deployed backend URLs - both must be HTTPS.
Store submission also needs: a privacy policy URL (required by both stores given this app requests microphone/camera/location), Play Store data-safety form answers, and an Apple App Store Connect listing. None of that is scaffolded here since it requires your legal/business decisions, not code.
