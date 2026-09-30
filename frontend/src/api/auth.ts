import apiClient from './client';
import type { LoginRequest, TokenResponse, User } from '../types/auth';

export const authApi = {
  login: async (payload: LoginRequest): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>('/auth/login', payload);
    return res.data;
  },

  me: async (): Promise<User> => {
    const res = await apiClient.get<User>('/auth/me');
    return res.data;
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout');
  },

  refresh: async (): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>('/auth/refresh');
    return res.data;
  },
};
