import axios from 'axios';

const defaultApiUrl =
  import.meta.env.DEV && typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : 'http://localhost:8000';

const baseURL = (import.meta.env.VITE_API_URL || defaultApiUrl).replace(/\/+$/, '');

const api = axios.create({
  baseURL,
});

// Automatically attach JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Automatically handle expired/invalid tokens
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && error.config?.url !== '/auth/login') {
      localStorage.removeItem('token');
      Object.keys(localStorage)
  .filter((k) => k.startsWith('placeiq_'))
  .forEach((k) => localStorage.removeItem(k));
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;