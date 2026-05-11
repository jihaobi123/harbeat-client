import apiClient from './client';
import type { APIResponse, VoiceCommandResponse } from '../types/api';

export const voiceApi = {
  sendCommand: (text: string, userId?: number, languageHint?: 'auto' | 'zh' | 'en') =>
    apiClient.post<APIResponse<VoiceCommandResponse>>('/voice/command', {
      text,
      user_id: userId,
      language_hint: languageHint ?? 'auto',
    }),
};
