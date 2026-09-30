import apiClient from './client';
import type { DashboardStats, RecentActivity } from '../types/land';

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    const res = await apiClient.get<DashboardStats>('/dashboard/stats');
    return res.data;
  },

  getActivity: async (): Promise<RecentActivity> => {
    const res = await apiClient.get<RecentActivity>('/dashboard/activity');
    return res.data;
  },
};
