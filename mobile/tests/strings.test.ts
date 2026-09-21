import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createStrings } from '../src/i18n/strings.ts';

const base = JSON.parse(readFileSync(new URL('../src/i18n/translations.base.json', import.meta.url), 'utf8'));
const extra = JSON.parse(readFileSync(new URL('../src/i18n/translations.extra.json', import.meta.url), 'utf8'));
const s = createStrings(base, extra);

test('translated strings are used; missing ones fall back to English, then to the key', () => {
  assert.notEqual(s.t('nav.report', 'hi'), s.t('nav.report', 'en'));
  assert.equal(s.t('nav.report', 'ta'), 'Report an Issue'); // extras exist in English+Hindi only -> English fallback
  assert.equal(s.isTranslated('nav.report', 'ta'), false);
  assert.equal(s.t('no.such.key', 'kn'), 'no.such.key');
  assert.equal(s.t('nav.report', 'xx'), 'Report an Issue');
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
  assert.ok(s.coverage('ta').translated < en.total);
});
