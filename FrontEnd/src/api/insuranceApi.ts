import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60s — agent calls can be slow
});

export type ResponseType = 'plan_selection' | 'coverage_info' | 'general';

export interface ChatResponse {
  reply: string;
  session_id: string;
  response_type: ResponseType;
  // plan_selection
  plans?: string[];
  // coverage_info
  specialty?: string;
  estimated_copay?: string;
  requires_authorization?: boolean;
  waiting_period_days?: number;
  network_tier?: string;
  providers?: string[];
  annual_deductible?: string;
  notes?: string;
  deductible_applies?: boolean;
}

export const uploadInsuranceDocument = async (file: File, nombreSeguro: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('nombre_seguro', nombreSeguro);

  const response = await api.post(
    '/api/v1/insurance/asdfhnjoasidjasidailosdiajsdqweqnwadsnjkdaushcasjkdaso/upload',
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
  );
  return response.data;
};

export const sendInsuranceChatMessage = async (
  message: string,
  sessionId: string,
): Promise<ChatResponse> => {
  const response = await api.post(
    '/api/v1/insurance/dnjfasndashdqweojgkpsdjfmmknsabdkodfpoiucxzcasdqwm/chat',
    { message, session_id: sessionId },
  );
  return response.data;
};
