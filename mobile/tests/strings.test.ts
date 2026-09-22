import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createStrings } from '../src/i18n/strings.ts';

const base = JSON.parse(readFileSync(new URL('../src/i18n/translations.base.json', import.meta.url), 'utf8'));
const extra = JSON.parse(readFileSync(new URL('../src/i18n/translations.extra.json', import.meta.url), 'utf8'));
const s = createStrings(base, extra);

test('translated strings are used; missing ones fall back to English, then to the key', () => {
  assert.notEqual(s.t('nav.report', 'hi'), s.t('nav.report', 'en'));
  assert.notEqual(s.t('nav.report', 'ta'), s.t('nav.report', 'en')); // now genuinely translated in all 7 languages, not a fallback
  assert.equal(s.isTranslated('nav.report', 'ta'), true);
  assert.equal(s.t('no.such.key', 'kn'), 'no.such.key');
  assert.equal(s.t('nav.report', 'xx'), 'Report an Issue');
});

test('fallback itself still works, exercised against a synthetic gap rather than a real one', () => {
  const gapStrings = createStrings({ en: { 'only.in.english': 'Only in English' } }, { en: {} });
  assert.equal(gapStrings.t('only.in.english', 'hi'), 'Only in English');
  assert.equal(gapStrings.isTranslated('only.in.english', 'hi'), false);
});

test('the brand is never transliterated (source dictionary transliterated it; the backend pins it, the app must too)', () => {
  assert.equal(s.t('brand', 'hi'), 'CivicLens');
});

test('mobile string files are byte-identical to the backend ones (no drift)', () => {
  const back = (n: string) => readFileSync(new URL(`../../app/i18n/${n}`, import.meta.url), 'utf8');
  assert.equal(readFileSync(new URL('../src/i18n/translations.base.json', import.meta.url), 'utf8'), back('translations.json'));
  assert.equal(readFileSync(new URL('../src/i18n/translations.extra.json', import.meta.url), 'utf8'), back('ui_extra.json'));
});

test('coverage is reported honestly', () => {
  const en = s.coverage('en');
  assert.equal(en.translated, en.total);
  assert.equal(s.coverage('ta').translated, en.total); // all 7 languages are fully translated now
  const gapStrings = createStrings({ en: { a: '1', b: '2' } }, { en: {} });
  assert.equal(gapStrings.coverage('hi').translated, 0); // a real gap still shows up, not hidden
});
