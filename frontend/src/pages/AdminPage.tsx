import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Users, Shield, FileText, Activity, Plus,
  CheckCircle, XCircle, Clock, Eye,
} from 'lucide-react';
import apiClient from '../api/client';
import { Breadcrumbs } from '../components/layout/Breadcrumbs';
import { formatDateTime, formatRelative } from '../utils/formatters';
import type { User } from '../types/auth';

type TabId = 'users' | 'audit';

async function fetchUsers() {
  const res = await apiClient.get('/admin/users');
  return res.data;
}

async function fetchAuditLogs() {
  const res = await apiClient.get('/admin/audit-logs');
  return res.data;
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    SUCCESS: 'var(--color-success-500)',
    ERROR:   'var(--color-error-500)',
  };
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8,
      borderRadius: '50%',
      background: colors[status] ?? 'var(--color-slate-400)',
      marginRight: 6,
    }} />
  );
}

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<TabId>('users');

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: fetchUsers,
    enabled: activeTab === 'users',
  });

  const { data: auditData, isLoading: auditLoading } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: fetchAuditLogs,
    enabled: activeTab === 'audit',
  });

  const tabs: { id: TabId; label: string; icon: React.ReactNode; count?: number }[] = [
    { id: 'users', label: 'User Management', icon: <Users size={14} />, count: usersData?.total },
    { id: 'audit', label: 'Audit Log', icon: <Activity size={14} />, count: auditData?.total },
  ];

  return (
    <div>
      <Breadcrumbs crumbs={[{ label: 'Admin Panel' }]} />

      <div className="demo-banner">
        <Shield size={14} />
        <span><strong>Admin Access Only.</strong> This panel is restricted to ADMIN role users.</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 'var(--space-6)', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-secondary)', color: 'var(--text-primary)' }}>
            Administration Panel
          </h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
            Manage users, roles, and view audit trails
          </p>
        </div>
        {activeTab === 'users' && (
          <button className="btn btn--primary btn--md" id="create-user-btn">
            <Plus size={14} /> Create User
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            id={`admin-tab-${tab.id}`}
          >
            {tab.icon}
            {tab.label}
            {tab.count != null && (
              <span className="tab__count">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Users tab */}
      {activeTab === 'users' && (
        <div className="data-table-wrap animate-fade-in">
          {usersLoading ? (
            <div style={{ padding: 'var(--space-6)' }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="skeleton" style={{ height: 44, marginBottom: 8 }} />
              ))}
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Full Name</th>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>District</th>
                  <th>Status</th>
                  <th>Last Login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {usersData?.items?.map((user: User) => (
                  <tr key={user.id}>
                    <td style={{ fontWeight: 500 }}>{user.full_name}</td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                        {user.username}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                      {user.email}
                    </td>
                    <td>
                      <span className={`role-badge role-badge--${user.role}`}>{user.role}</span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                      {user.district_code ?? '—'}
                    </td>
                    <td>
                      {user.is_active ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-success-600)', fontSize: 'var(--text-sm)' }}>
                          <CheckCircle size={13} /> Active
                        </span>
                      ) : (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-error-600)', fontSize: 'var(--text-sm)' }}>
                          <XCircle size={13} /> Inactive
                        </span>
                      )}
                    </td>
                    <td style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
                      {user.last_login ? formatRelative(user.last_login) : '—'}
                    </td>
                    <td>
                      <button className="btn btn--ghost btn--xs" title="View user">
                        <Eye size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Audit log tab */}
      {activeTab === 'audit' && (
        <div className="data-table-wrap animate-fade-in">
          {auditLoading ? (
            <div style={{ padding: 'var(--space-6)' }}>
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="skeleton" style={{ height: 36, marginBottom: 8 }} />
              ))}
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>Resource ID</th>
                  <th>Actor</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {auditData?.items?.map((log: Record<string, string>) => (
                  <tr key={log._id}>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                      {log.timestamp ? formatDateTime(log.timestamp) : '—'}
                    </td>
                    <td>
                      <code style={{
                        fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                        background: 'var(--color-slate-100)',
                        padding: '2px 6px', borderRadius: 'var(--radius-xs)',
                        color: 'var(--color-navy-800)',
                      }}>
                        {log.action}
                      </code>
                    </td>
                    <td style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                      {log.resource_type}
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                        {log.resource_id ? log.resource_id.slice(0, 12) + '…' : '—'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                      {log.actor_id ? log.actor_id.slice(0, 12) + '…' : 'system'}
                    </td>
                    <td>
                      <span style={{ fontSize: 'var(--text-sm)' }}>
                        <StatusDot status={log.status} />
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {!auditData?.items?.length && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 'var(--space-8)', color: 'var(--text-secondary)' }}>
                      No audit events yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
