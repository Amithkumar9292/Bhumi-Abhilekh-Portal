/**
 * useTranslation hook — access translations and language state throughout the app
 *
 * Usage:
 *   const { t, lang, setLang } = useTranslation();
 *   <button>{t('action.save')}</button>
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import {
  t as _t, TranslationKey, LANGUAGES, LangMeta,
  applyLanguage, getPersistedLang, persistLang,
} from './index';

// ── Context ───────────────────────────────────────────────────────────────────

interface I18nContextValue {
  lang: string;
  langMeta: LangMeta;
  setLang: (code: string) => void;
  t: (key: TranslationKey) => string;
  languages: LangMeta[];
  isRTL: boolean;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<string>(getPersistedLang);

  const setLang = useCallback((code: string) => {
    setLangState(code);
    persistLang(code);
    applyLanguage(code);
  }, []);

  // Apply on mount and whenever lang changes
  useEffect(() => {
    applyLanguage(lang);
  }, [lang]);

  const langMeta = LANGUAGES.find(l => l.code === lang) ?? LANGUAGES[0];

  const translate = useCallback(
    (key: TranslationKey) => _t(key, lang),
    [lang],
  );

  return (
    <I18nContext.Provider value={{
      lang, langMeta, setLang, t: translate,
      languages: LANGUAGES, isRTL: langMeta.dir === 'rtl',
    }}>
      {children}
    </I18nContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useTranslation must be used inside I18nProvider');
  return ctx;
}
