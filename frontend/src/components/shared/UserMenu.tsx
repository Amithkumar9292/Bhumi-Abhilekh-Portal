import React, { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  User, Settings, LogOut, Shield, ChevronDown, HelpCircle,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { authApi } from '../../api/auth';

export function UserMenu() {
  const { user, clearAuth } = useAuthStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const initials = user?.full_name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() ?? '??';

  async function handleLogout() {
    try {
      await authApi.logout();
    } catch { /* ignore */ }
    clearAuth();
    navigate('/login');
  }

  if (!user) return null;

  return (
    <div className="user-menu" ref={ref}>
      <button
        className="user-menu__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="User menu"
        id="user-menu-btn"
      >
        <div className="user-menu__avatar" aria-hidden="true">{initials}</div>
        <span className="user-menu__name">{user.full_name.split(' ')[0]}</span>
        <ChevronDown
          size={13}
          style={{
            color: 'var(--text-tertiary)',
            transform: open ? 'rotate(180deg)' : 'none',
            transition: 'transform var(--transition-fast)',
          }}
        />
      </button>

      {open && (
        <div className="user-menu__dropdown" role="menu">
          <div className="user-menu__header">
            <div className="user-menu__user-name">{user.full_name}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <span className={`role-badge role-badge--${user.role}`}>{user.role}</span>
              {user.district_code && (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                  {user.district_code}
                </span>
              )}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>
              {user.email}
            </div>
          </div>

          <Link
            to="/profile"
            className="user-menu__item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <User size={14} /> My Profile
          </Link>

          {user.role === 'ADMIN' && (
            <Link
              to="/admin"
              className="user-menu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <Shield size={14} /> Admin Panel
            </Link>
          )}

          <Link
            to="/settings"
            className="user-menu__item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <Settings size={14} /> Settings
          </Link>

          <Link
            to="/help"
            className="user-menu__item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <HelpCircle size={14} /> Help & Support
          </Link>

          <div className="user-menu__divider" role="separator" />

          <button
            className="user-menu__item user-menu__item--danger"
            role="menuitem"
            onClick={handleLogout}
            style={{ width: '100%', textAlign: 'left', border: 'none', background: 'none', font: 'inherit' }}
          >
            <LogOut size={14} /> Sign Out
          </button>
        </div>
      )}
    </div>
  );
}
