import apiClient from './client';
import type {
  APIResponse,
  StyleMixRequest,
  StyleMixResult,
  DjMixPlanRequest,
  DjMixPlanResult,
  DjOfflineMixRequest,
  DjOfflineMixResult,
} from '../types/api';

export const mixApi = {
  generateStyleMix: (data: StyleMixRequest) =>
    apiClient.post<APIResponse<StyleMixResult>>('/playlists/generate-style-mix', data),

  generateDjMixPlan: (data: DjMixPlanRequest) =>
    apiClient.post<APIResponse<DjMixPlanResult>>('/playlists/generate-dj-mix-plan', data),

  generateOfflineMix: (data: DjOfflineMixRequest) =>
    apiClient.post<APIResponse<DjOfflineMixResult>>('/playlists/generate-dj-offline-mix', data),
};

export function getStreamUrl(filename: string): string {
  const token = localStorage.getItem('harbeat_token');
  return `/api/stream/mixes/${filename}?token=${token ?? ''}`;
}

export function getProcessedStreamUrl(filename: string): string {
  const token = localStorage.getItem('harbeat_token');
  return `/api/stream/processed/${filename}?token=${token ?? ''}`;
}

export function getLibraryStreamUrl(songId: string | number): string {
  const token = localStorage.getItem('harbeat_token');
  return `/api/stream/${songId}?token=${token ?? ''}`;
}
