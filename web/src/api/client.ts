import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 300_000, // 5 min for offline mix generation
});

// Request interceptor: inject JWT
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('harbeat_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: keep demo/dev pages on-screen for 401s instead of redirecting.
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !window.location.pathname.startsWith('/mix-lab')) {
      localStorage.removeItem('harbeat_token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

export default apiClient;
