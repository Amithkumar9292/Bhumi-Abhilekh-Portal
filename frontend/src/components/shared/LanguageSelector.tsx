import React, { useState, useRef, useEffect } from 'react';
import { Globe, Check, ChevronDown } from 'lucide-react';
import { useTranslation } from '../../i18n/useTranslation';
import { LANGUAGES } from '../../i18n/index';

// Show these languages prominently; others in a "More" section
const PRIMARY_LANGS = ['en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn'];

export function LanguageSelector() {
  const { lang, setLang, langMeta } = useTranslation();
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setShowAll(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const primaryLangs = LANGUAGES.filter(l => PRIMARY_LANGS.includes(l.code));
  const moreLangs = LANGUAGES.filter(l => !PRIMARY_LANGS.includes(l.code));

  return (
    <div className="lang-selector" ref={ref}>
      <button
        className="lang-selector__btn"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Select language"
        id="lang-selector-btn"
        title="Change language / भाषा बदलें"
      >
        <Globe size={13} />
        <span style={{ fontFamily: langMeta.fontFamily ?? 'inherit' }}>
          {langMeta.nativeName}
        </span>
        <ChevronDown size={10} style={{ opacity: 0.6, transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'none' }} />
      </button>

      {open && (
        <div
          className="lang-selector__dropdown"
          role="listbox"
          aria-label="Select language"
          style={{ minWidth: 220, maxHeight: 360, overflowY: 'auto' }}
        >
          {/* Schedule notice */}
          <div style={{ padding: '6px 12px 4px', fontSize: 9, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid var(--border-default)' }}>
            Language / भाषा
          </div>

          {primaryLangs.map(l => (
            <LangOption key={l.code} lang={l} current={lang} onSelect={(c) => { setLang(c); setOpen(false); }} />
          ))}

          {/* More languages */}
          <button
            style={{ width: '100%', padding: '6px 12px', fontSize: 11, color: 'var(--color-navy-700)', background: 'var(--color-navy-50)', border: 'none', cursor: 'pointer', fontWeight: 600, textAlign: 'left', borderTop: '1px solid var(--border-default)' }}
            onClick={() => setShowAll(s => !s)}
          >
            {showAll ? '▲ Show less' : `▼ More languages (${moreLangs.length})`}
          </button>

          {showAll && moreLangs.map(l => (
            <LangOption key={l.code} lang={l} current={lang} onSelect={(c) => { setLang(c); setOpen(false); setShowAll(false); }} />
          ))}

          <div style={{ padding: '4px 12px 6px', fontSize: 9, color: 'var(--text-tertiary)', borderTop: '1px solid var(--border-default)' }}>
            22 languages · 8th Schedule of Constitution of India
          </div>
        </div>
      )}
    </div>
  );
}

function LangOption({ lang, current, onSelect }: {
  lang: typeof LANGUAGES[number];
  current: string;
  onSelect: (code: string) => void;
}) {
  const isSelected = lang.code === current;
  return (
    <div
      className={`lang-selector__option${isSelected ? ' lang-selector__option--active' : ''}`}
      role="option"
      aria-selected={isSelected}
      onClick={() => onSelect(lang.code)}
      style={{ direction: lang.dir }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span style={{ fontFamily: lang.fontFamily ?? 'inherit', fontSize: 13, fontWeight: 600 }}>
          {lang.nativeName}
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{lang.name}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
        {lang.scheduleLang && (
          <span style={{ fontSize: 8, background: 'var(--color-navy-100)', color: 'var(--color-navy-700)', padding: '1px 4px', borderRadius: 2, fontWeight: 700 }}>8th</span>
        )}
        {isSelected && <Check size={12} className="lang-selector__check" />}
      </div>
    </div>
  );
}
