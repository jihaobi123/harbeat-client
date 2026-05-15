import apiClient from './client';
import type {
  APIResponse,
  FangpiSearchSong,
  MixtapeImportResult,
  MixtapeImportSong,
  MixtapeVibeSearchData,
  ParsedPlaylistData,
  TrackSegmentName,
} from '../types/api';

export interface MixtapeVibeSearchRequest {
  vibe?: string;
  tags?: string[];
  mode?: 'style' | 'vibe';
  limit?: number;
}

export interface MixtapeImportSongsRequest {
  playlist_id?: number;
  playlist_name?: string;
  songs: MixtapeImportSong[];
}

export interface PlaylistSegmentChoice {
  index?: number;
  title?: string;
  artist?: string;
  segment: TrackSegmentName;
}

export interface MixtapeImportPlaylistRequest {
  url: string;
  playlist_id?: number;
  playlist_name?: string;
  default_segment?: TrackSegmentName;
  track_segments?: PlaylistSegmentChoice[];
  limit?: number;
}

export interface MixtapeImportPlaylistResult extends MixtapeImportResult {
  platform?: string;
  source_name?: string;
  track_count: number;
}

export const mixtapeApi = {
  vibeSearch: (data: MixtapeVibeSearchRequest) =>
    apiClient.post<APIResponse<MixtapeVibeSearchData>>('/fangpi/vibe-search', data),

  search: (query: string) =>
    apiClient.post<APIResponse<{ songs: FangpiSearchSong[] }>>('/fangpi/search', { query }),

  parsePlaylist: (url: string) =>
    apiClient.post<APIResponse<ParsedPlaylistData>>('/fangpi/parse-playlist', { url }),

  importSongs: (data: MixtapeImportSongsRequest) =>
    apiClient.post<APIResponse<MixtapeImportResult>>('/fangpi/import-songs', data),

  importPlaylist: (data: MixtapeImportPlaylistRequest) =>
    apiClient.post<APIResponse<MixtapeImportPlaylistResult>>('/fangpi/import-playlist', data),

  reanalyzeAll: (force = true) =>
    apiClient.post<APIResponse<{ updated: number; skipped: number; failed: unknown[] }>>('/library/reanalyze-all', { force }),
};
