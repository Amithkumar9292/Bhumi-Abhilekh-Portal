import apiClient from './client';
import type {
  LandRecord,
  LandRecordCreate,
  LandRecordListItem,
  PaginatedResponse,
} from '../types/land';

export interface ListLandRecordsParams {
  page?: number;
  page_size?: number;
  status?: string;
  district?: string;
  search?: string;
}

export const landRecordsApi = {
  list: async (params: ListLandRecordsParams = {}): Promise<PaginatedResponse<LandRecordListItem>> => {
    const res = await apiClient.get<PaginatedResponse<LandRecordListItem>>('/land-records', { params });
    return res.data;
  },

  get: async (id: string): Promise<LandRecord> => {
    const res = await apiClient.get<LandRecord>(`/land-records/${id}`);
    return res.data;
  },

  create: async (payload: LandRecordCreate): Promise<LandRecord> => {
    const res = await apiClient.post<LandRecord>('/land-records', payload);
    return res.data;
  },

  update: async (id: string, payload: Partial<LandRecordCreate>): Promise<LandRecord> => {
    const res = await apiClient.put<LandRecord>(`/land-records/${id}`, payload);
    return res.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/land-records/${id}`);
  },

  verify: async (id: string, payload: { approved: boolean; rejection_reason?: string }): Promise<LandRecord> => {
    const res = await apiClient.post<LandRecord>(`/land-records/${id}/verify`, payload);
    return res.data;
  },
};
