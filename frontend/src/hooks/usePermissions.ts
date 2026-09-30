import { useAuthStore } from '../store/authStore';
import type { UserRole } from '../types/auth';

/**
 * RBAC permission hook.
 * Usage: const { can } = usePermissions();
 *        if (can('create:records')) { ... }
 */
export function usePermissions() {
  const { user } = useAuthStore();
  const role = user?.role ?? null;

  /** Returns true if the user's role is in the allowed list */
  function hasRole(...roles: UserRole[]): boolean {
    return role !== null && roles.includes(role);
  }

  const permissions = {
    // Records
    'view:records':   hasRole('ADMIN', 'OFFICER', 'VERIFIER', 'VIEWER'),
    'create:records': hasRole('ADMIN', 'OFFICER'),
    'edit:records':   hasRole('ADMIN', 'OFFICER'),
    'delete:records': hasRole('ADMIN'),
    'verify:records': hasRole('ADMIN', 'VERIFIER'),

    // Documents
    'upload:documents':   hasRole('ADMIN', 'OFFICER'),
    'validate:documents': hasRole('ADMIN', 'VERIFIER'),

    // Admin
    'view:admin':        hasRole('ADMIN'),
    'manage:users':      hasRole('ADMIN'),
    'view:audit-logs':   hasRole('ADMIN'),

    // Reports
    'view:reports': hasRole('ADMIN', 'OFFICER'),
  } as const;

  type Permission = keyof typeof permissions;

  function can(permission: Permission): boolean {
    return permissions[permission] ?? false;
  }

  return { can, hasRole, role, permissions };
}
