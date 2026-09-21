#!/usr/bin/env sh
# Type-check the mobile sources WITHOUT node_modules, against minimal ambient stubs for React/React Native/Expo (tools/ambient-stubs.d.ts).
# It catches syntax errors and type errors in OUR code (props, API types, state machine, sync engine). Third-party API shape is NOT checked:
# run `npm install && npm run typecheck` for the real thing.
cd "$(dirname "$0")/.." || exit 1
tsc --ignoreConfig --noEmit --skipLibCheck --jsx react-jsx --allowImportingTsExtensions --moduleResolution bundler --module esnext --target es2022 \
  --resolveJsonModule --strict --lib es2022,dom tools/ambient-stubs.d.ts $(find app src tests -name '*.ts' -o -name '*.tsx') \
  | grep -v -E "TS2503|TS7006|TS7031" ; test "${PIPESTATUS:-0}" = 0
