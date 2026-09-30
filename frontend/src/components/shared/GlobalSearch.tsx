import React, { useState, useRef, useEffect } from 'react';
import { Search } from 'lucide-react';

interface GlobalSearchProps {
  placeholder?: string;
}

export function GlobalSearch({ placeholder = 'Search khasra, owner, district…' }: GlobalSearchProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Ctrl+K shortcut
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div className="global-search">
      <div className="global-search__input-wrap">
        <Search className="global-search__icon" aria-hidden="true" />
        <input
          ref={inputRef}
          type="search"
          className="global-search__input"
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Global search"
          id="global-search-input"
        />
        <div className="global-search__kbd" aria-hidden="true">
          <span className="kbd">Ctrl</span>
          <span className="kbd">K</span>
        </div>
      </div>
    </div>
  );
}
