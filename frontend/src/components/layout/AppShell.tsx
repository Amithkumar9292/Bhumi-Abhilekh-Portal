import React from 'react';
import { GovHeader } from './GovHeader';

interface AppShellProps { children: React.ReactNode; }

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <GovHeader />
      <main className="main-content" id="main-content">
        <div className="page-wrap">
          {children}
        </div>
      </main>
      <footer className="app-footer">
        <span>© 2024 Ministry of Rural Development, Government of India</span>
        <span className="app-footer__warn">⚠ Demo System — Synthetic Data Only. Not Legally Binding.</span>
        <span>v1.0.0-demo</span>
      </footer>
    </div>
  );
}
