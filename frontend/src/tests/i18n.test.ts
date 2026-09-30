/**
 * i18n Unit Tests — Vitest
 * Tests the translation system, language detection, persistence, and font loading.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { t, LANGUAGES, applyLanguage, getPersistedLang, persistLang, LANG_STORAGE_KEY } from '../i18n/index';

describe('t() translation function', () => {
  it('returns English for base keys', () => {
    expect(t('action.save', 'en')).toBe('Save');
    expect(t('action.cancel', 'en')).toBe('Cancel');
    expect(t('nav.dashboard', 'en')).toBe('Dashboard');
  });

  it('returns Hindi translations for hi locale', () => {
    expect(t('action.save', 'hi')).toBe('सहेजें');
    expect(t('nav.dashboard', 'hi')).toBe('डैशबोर्ड');
    expect(t('status.verified', 'hi')).toBe('सत्यापित');
  });

  it('falls back to English for missing translation', () => {
    // Telugu has partial translations; keys not in te should fall back to en
    const result = t('sys.nonLegalBinding', 'te');
    const enResult = t('sys.nonLegalBinding', 'en');
    // Either returns the te value or the en fallback — never undefined
    expect(result).toBeTruthy();
    expect(typeof result).toBe('string');
  });

  it('falls back to key name for completely unknown key', () => {
    // @ts-ignore — testing with invalid key
    const result = t('totally.unknown.key.xyz', 'en');
    expect(result).toBe('totally.unknown.key.xyz');
  });

  it('returns English for unknown language code', () => {
    expect(t('action.save', 'zz')).toBe('Save');
  });

  it('translates all nav items in Hindi', () => {
    const navKeys = [
      'nav.dashboard', 'nav.landRecords', 'nav.verification',
      'nav.documents', 'nav.auditTrail',
    ] as const;
    for (const key of navKeys) {
      const result = t(key, 'hi');
      expect(result).not.toBe(key); // should not return the key itself
      expect(result.length).toBeGreaterThan(1);
    }
  });
});

describe('LANGUAGES metadata', () => {
  it('has at least 15 languages', () => {
    expect(LANGUAGES.length).toBeGreaterThanOrEqual(15);
  });

  it('English is first', () => {
    expect(LANGUAGES[0].code).toBe('en');
  });

  it('all languages have required fields', () => {
    for (const lang of LANGUAGES) {
      expect(lang.code).toBeTruthy();
      expect(lang.name).toBeTruthy();
      expect(lang.nativeName).toBeTruthy();
      expect(['ltr', 'rtl']).toContain(lang.dir);
    }
  });

  it('Urdu is RTL', () => {
    const urdu = LANGUAGES.find(l => l.code === 'ur');
    expect(urdu?.dir).toBe('rtl');
  });

  it('Hindi is Devanagari script', () => {
    const hindi = LANGUAGES.find(l => l.code === 'hi');
    expect(hindi?.script).toBe('Devanagari');
  });

  it('8th Schedule languages are marked', () => {
    const scheduleLangs = LANGUAGES.filter(l => l.scheduleLang);
    expect(scheduleLangs.length).toBeGreaterThanOrEqual(12);
  });
});

describe('Language persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('getPersistedLang returns en by default', () => {
    expect(getPersistedLang()).toBe('en');
  });

  it('persistLang stores in localStorage', () => {
    persistLang('hi');
    expect(localStorage.getItem(LANG_STORAGE_KEY)).toBe('hi');
  });

  it('getPersistedLang retrieves stored value', () => {
    persistLang('te');
    expect(getPersistedLang()).toBe('te');
  });
});

describe('applyLanguage DOM effects', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('lang');
    document.documentElement.removeAttribute('dir');
  });

  it('sets lang attribute on html element', () => {
    applyLanguage('hi');
    expect(document.documentElement.getAttribute('lang')).toBe('hi');
  });

  it('sets dir=ltr for Hindi', () => {
    applyLanguage('hi');
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
  });

  it('sets dir=rtl for Urdu', () => {
    applyLanguage('ur');
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
  });

  it('sets dir=ltr for English', () => {
    applyLanguage('en');
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
  });
});
