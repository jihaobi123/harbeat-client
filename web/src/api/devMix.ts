import apiClient from './client';
import type { APIResponse, DjMixPlanResult } from '../types/api';

export interface DevSongItem {
  library_song_id: string;
  song_id: number;
  title: string;
  artist: string;
  duration: number;
  bpm?: number | null;
  key?: string | null;
  camelot_key?: string | null;
  energy?: number | null;
  analysis_status?: string | null;
  stream_url: string;
}

export interface DevSongList {
  user_id: number;
  songs: DevSongItem[];
}

export interface DevPlanRequest {
  style?: string;
  duration_minutes?: number;
  quality_mode?: 'balanced' | 'hq' | 'fast';
  random_seed?: number | null;
  diversity?: number;
  candidate_window?: number;
  max_tracks?: number;
  song_ids?: number[];
  target_energy_curve?: number[] | null;
}

export const devMixApi = {
  listSongs: (limit = 24) =>
    apiClient.get<APIResponse<DevSongList>>('/dev/songs', { params: { limit } }),

  generateMixPlan: (data: DevPlanRequest) =>
    apiClient.post<APIResponse<DjMixPlanResult>>('/dev/mix-plan', data),
};

export function getDevLibraryStreamUrl(librarySongId: string | number): string {
  return `/api/dev/songs/${librarySongId}/stream`;
}
