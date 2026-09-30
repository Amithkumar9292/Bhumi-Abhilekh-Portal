import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { useNavigate } from 'react-router-dom';

export function useAuth() {
  const { user, isAuthenticated, token, setAuth, setUser, clearAuth } = useAuthStore();
  const navigate = useNavigate();

  async function logout() {
    try {
      await authApi.logout();
    } catch {
      // Ignore errors — always clear local state
    }
    clearAuth();
    navigate('/login', { replace: true });
  }

  async function refreshUser() {
    try {
      const fresh = await authApi.me();
      setUser(fresh);
      return fresh;
    } catch {
      return null;
    }
  }

  return {
    user,
    isAuthenticated,
    token,
    logout,
    refreshUser,
  };
}
