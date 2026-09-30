import React from 'react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg-body)', padding: 'var(--space-8)',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 80, marginBottom: 'var(--space-4)' }}>🗺️</div>
      <h1 style={{
        fontSize: 'var(--text-4xl)', fontWeight: 700,
        color: 'var(--text-primary)', marginBottom: 'var(--space-2)',
        fontFamily: 'var(--font-secondary)',
      }}>
        404 — Page Not Found
      </h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-6)', maxWidth: 400 }}>
        The page you are looking for doesn't exist or has been moved.
      </p>
      <Link to="/dashboard" className="btn btn--primary btn--lg">
        Return to Dashboard
      </Link>
    </div>
  );
}
