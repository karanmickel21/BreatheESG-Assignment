import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const orig = err.config;
    if (err.response?.status === 401 && !orig._retry) {
      orig._retry = true;
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/api/auth/token/refresh/`, { refresh });
          localStorage.setItem('access_token', data.access);
          orig.headers.Authorization = `Bearer ${data.access}`;
          return api(orig);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(err);
  }
);

export default api;

// --- Auth ---
export const login = (username, password) =>
  api.post('/auth/token/', { username, password });

export const getMe = () => api.get('/me/');

// --- Dashboard ---
export const getDashboard = () => api.get('/dashboard/');

// --- Records ---
export const getRecords = (params) => api.get('/records/', { params });
export const approveRecord = (id, notes) => api.post(`/records/${id}/approve/`, { notes });
export const rejectRecord = (id, notes) => api.post(`/records/${id}/reject/`, { notes });
export const flagRecord = (id, reason) => api.post(`/records/${id}/flag/`, { reason });
export const lockRecord = (id) => api.post(`/records/${id}/lock/`);
export const bulkApprove = (ids) => api.post('/records/bulk-approve/', { ids });
export const getRecordHistory = (id) => api.get(`/records/${id}/history/`);

// --- Ingestion ---
export const uploadFile = (source_type, file) => {
  const form = new FormData();
  form.append('source_type', source_type);
  form.append('file', file);
  return api.post('/ingestion/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};
export const getBatches = () => api.get('/ingestion/');

// --- Facilities ---
export const getFacilities = () => api.get('/facilities/');
