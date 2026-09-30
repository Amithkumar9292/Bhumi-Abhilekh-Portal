import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/**
 * Default timeout for ordinary API calls.
 *
 * This is deliberately short. Document upload no longer waits for OCR -- it
 * returns 202 as soon as the file is stored and queued -- so nothing on the
 * upload path legitimately takes 30 seconds. Endpoints that do heavy synchronous
 * work (exports, bulk queries) opt into a longer timeout per request instead of
 * raising this global ceiling, which keeps a stuck request from pinning a
 * connection for half a minute.
 */
export const DEFAULT_TIMEOUT_MS = 15_000;

/** Uploads only persist bytes and enqueue, so they stay well under this. */
export const UPLOAD_TIMEOUT_MS = 60_000;

/** Status polling and other frequent small reads. */
export const POLL_TIMEOUT_MS = 10_000;

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: DEFAULT_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // send cookies for refresh token
});

// ── Request interceptor: attach access token ─────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = JSON.parse(localStorage.getItem('bhumi-auth') || '{}')?.state?.token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor: handle 401 → refresh ───────────────
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: string) => void;
  reject: (reason: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error);
    else prom.resolve(token!);
  });
  failedQueue = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const res = await axios.post(
          `${API_BASE}/api/v1/auth/refresh`,
          {},
          { withCredentials: true }
        );
        const newToken: string = res.data.access_token;
        // Patch the Zustand bhumi-auth store so the request interceptor
        // (which reads from that key) immediately picks up the new token.
        try {
          const stored = JSON.parse(localStorage.getItem('bhumi-auth') || '{}');
          if (stored?.state) {
            stored.state.token = newToken;
            localStorage.setItem('bhumi-auth', JSON.stringify(stored));
          }
        } catch {
          // If parsing fails, fall back to a bare key so something is saved.
          localStorage.setItem('access_token', newToken);
        }
        apiClient.defaults.headers.common.Authorization = `Bearer ${newToken}`;
        processQueue(null, newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.removeItem('access_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
