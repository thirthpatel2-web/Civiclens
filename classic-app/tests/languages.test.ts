import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LANGUAGES, isLanguageCode, scriptHistogram, scriptMatches } from '../src/i18n/languages.ts';
import { ENGLISH_TRANSLATION, SAMPLES } from './helpers.ts';

test('registry covers the target languages with native names', () => {
  assert.deepEqual(Object.keys(LANGUAGES).sort(), ['bn', 'en', 'gu', 'hi', 'kn', 'ml', 'mr', 'pa', 'ta', 'te']);
  assert.equal(LANGUAGES.kn.native, 'ಕನ್ನಡ');
  assert.equal(isLanguageCode('kn'), true);
  assert.equal(isLanguageCode('xx'), false);
});

test('native-script samples match their own language script, and English does not match Kannada', () => {
  for (const [code, text] of Object.entries(SAMPLES)) assert.equal(scriptMatches(code as any, text), true, code);
  assert.equal(scriptMatches('kn', ENGLISH_TRANSLATION), false);
  assert.equal(scriptMatches('hi', SAMPLES.kn), false);
  assert.equal(scriptMatches('kn', 'ನನ್ನ road ನಲ್ಲಿ ಗುಂಡಿ ಇದೆ 123'), true); // code-mixed text
  assert.deepEqual(scriptHistogram('abc ಕ'), { Latn: 3, Knda: 1 });
});
