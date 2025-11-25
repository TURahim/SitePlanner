/**
 * Axios API client configuration
 */
import axios from 'axios';
import { fetchAuthSession } from '@aws-amplify/auth';
import { config } from './config';

export const api = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use(async (requestConfig) => {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) {
      requestConfig.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // Not authenticated - continue without token
  }
  return requestConfig;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login on auth failure
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

