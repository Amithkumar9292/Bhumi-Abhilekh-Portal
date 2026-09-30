import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface ToastNotification {
  id: string;
  title: string;
  description?: string;
  type: 'info' | 'success' | 'warning' | 'error';
  timestamp: Date;
  read: boolean;
  duration?: number; // ms, 0 = sticky
}

interface UIStore {
  language: string;     // IETF tag: 'en', 'hi', 'te', etc.
  theme: 'light' | 'dark' | 'system';
  sidebarCollapsed: boolean;
  notifications: ToastNotification[];
  toasts: ToastNotification[];

  setLanguage: (lang: string) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setSidebarCollapsed: (v: boolean) => void;
  addNotification: (n: Omit<ToastNotification, 'id' | 'timestamp' | 'read'>) => void;
  addToast: (n: Omit<ToastNotification, 'id' | 'timestamp' | 'read'>) => void;
  dismissToast: (id: string) => void;
  markAllRead: () => void;
  markRead: (id: string) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      language: 'en',
      theme: 'light',
      sidebarCollapsed: false,
      notifications: [
        { id: '1', title: 'Record KH-10142 Verified', description: 'Verified by verifier_priya · Lucknow', type: 'success', timestamp: new Date(Date.now() - 300000), read: false },
        { id: '2', title: '3 Anomalies Detected', description: 'Boundary overlap found in Agra district', type: 'warning', timestamp: new Date(Date.now() - 3600000), read: false },
        { id: '3', title: 'Document Processed', description: 'Title deed for KH-10089 validated', type: 'info', timestamp: new Date(Date.now() - 10800000), read: true },
      ],
      toasts: [],

      setLanguage: (lang) => set({ language: lang }),
      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),

      addNotification: (n) =>
        set((s) => ({
          notifications: [
            { ...n, id: crypto.randomUUID(), timestamp: new Date(), read: false },
            ...s.notifications,
          ],
        })),

      addToast: (n) =>
        set((s) => ({
          toasts: [
            { ...n, id: crypto.randomUUID(), timestamp: new Date(), read: false },
            ...s.toasts,
          ],
        })),

      dismissToast: (id) =>
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

      markAllRead: () =>
        set((s) => ({
          notifications: s.notifications.map((n) => ({ ...n, read: true })),
        })),

      markRead: (id) =>
        set((s) => ({
          notifications: s.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
        })),
    }),
    {
      name: 'bhumi-ui-store',
      partialize: (s) => ({ language: s.language, theme: s.theme, sidebarCollapsed: s.sidebarCollapsed }),
    },
  ),
);
