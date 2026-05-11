import apiClient from './client';
import type { APIResponse, TokenData, LoginRequest, RegisterRequest } from '../types/api';

export const authApi = {
  login: (data: LoginRequest) =>
    apiClient.post<APIResponse<TokenData>>('/auth/login', data),

  register: (data: RegisterRequest) =>
    apiClient.post<APIResponse<TokenData>>('/auth/register', data),

  refresh: (refreshToken: string) =>
    apiClient.post<APIResponse<TokenData>>('/auth/refresh', { refresh_token: refreshToken }),

  me: () =>
    apiClient.get<APIResponse<TokenData>>('/auth/me'),
};
