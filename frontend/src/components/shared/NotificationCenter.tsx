import React, { useState, useRef, useEffect } from 'react';
import { Bell, CheckCheck, AlertTriangle, CheckCircle, Info, XCircle } from 'lucide-react';
import { useUIStore } from '../../store/uiStore';
import { formatDistanceToNow } from 'date-fns';
import clsx from 'clsx';

const ICON_MAP = {
  info:    <Info size={14} />,
  success: <CheckCircle size={14} />,
  warning: <AlertTriangle size={14} />,
  error:   <XCircle size={14} />,
};

const COLOR_MAP = {
  info:    { bg: 'var(--color-info-100)',    color: 'var(--color-info-600)' },
  success: { bg: 'var(--color-success-100)', color: 'var(--color-success-600)' },
  warning: { bg: 'var(--color-warning-100)', color: 'var(--color-warning-600)' },
  error:   { bg: 'var(--color-error-100)',   color: 'var(--color-error-600)' },
};

export function NotificationCenter() {
  const { notifications, markAllRead } = useUIStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button
        className="icon-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        aria-haspopup="true"
        aria-expanded={open}
        id="notifications-btn"
      >
        <Bell size={17} />
        {unreadCount > 0 && (
          <span className="icon-btn__badge" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          <div className="notification-panel__header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <span className="notification-panel__title">Notifications</span>
              {unreadCount > 0 && (
                <span className="notification-panel__count">{unreadCount} new</span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                className="btn btn--ghost btn--xs"
                onClick={markAllRead}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                <CheckCheck size={13} />
                Mark all read
              </button>
            )}
          </div>

          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <div className="empty-state" style={{ padding: 'var(--space-8)' }}>
                <Bell size={32} style={{ opacity: 0.3, marginBottom: 'var(--space-2)' }} />
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map((n) => {
                const colors = COLOR_MAP[n.type];
                return (
                  <div
                    key={n.id}
                    className={clsx('notification-item', !n.read && 'notification-item--unread')}
                  >
                    <div
                      className="notification-item__icon"
                      style={{ background: colors.bg, color: colors.color }}
                    >
                      {ICON_MAP[n.type]}
                    </div>
                    <div className="notification-item__body">
                      <div className="notification-item__title">{n.title}</div>
                      <div className="notification-item__desc">{n.description}</div>
                    </div>
                    <div className="notification-item__time">
                      {formatDistanceToNow(n.timestamp, { addSuffix: true })}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
