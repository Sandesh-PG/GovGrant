import { GrantReport } from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem('auth_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    localStorage.removeItem('auth_token');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'API request failed');
  }

  return response.json();
}

export const api = {
  createSession: () => fetchWithAuth('/api/sessions', { method: 'POST' }),
  listSessions: () => fetchWithAuth('/api/sessions'),
  getResults: (sessionId: string): Promise<GrantReport> => 
    fetchWithAuth(`/api/results/${sessionId}`),
  createAlerts: (data: { session_id: string; email: string; whatsapp_enabled: boolean; phone?: string }) =>
    fetchWithAuth('/api/alerts', { method: 'POST', body: JSON.stringify(data) }),
  getAlerts: (sessionId: string) => fetchWithAuth(`/api/alerts/${sessionId}`),
};
