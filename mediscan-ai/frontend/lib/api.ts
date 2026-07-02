// Typed fetch client for the FastAPI backend. One module, no axios
// dependency — fetch is sufficient and keeps the bundle smaller.

import {
  AnalysisResponse,
  ApiError,
  ApiErrorBody,
  ChatResponse,
  HealthResponse,
  SessionHistoryResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: ApiErrorBody;
    try {
      body = await res.json();
    } catch {
      body = { code: "unknown_error", message: res.statusText, details: {} };
    }
    throw new ApiError(body, res.status);
  }
  return res.json() as Promise<T>;
}

export async function uploadAndAnalyze(
  file: File,
  sessionId: string
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<AnalysisResponse>(res);
}

export async function askFollowUp(
  analysisId: string,
  sessionId: string,
  question: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE_URL}/analyze/${analysisId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
  return handleResponse<ChatResponse>(res);
}

export async function getHistory(
  sessionId: string
): Promise<SessionHistoryResponse> {
  const res = await fetch(`${API_BASE_URL}/history/${sessionId}`);
  return handleResponse<SessionHistoryResponse>(res);
}

export async function getHistoryAnalysis(
  sessionId: string,
  analysisId: string
): Promise<AnalysisResponse> {
  const res = await fetch(`${API_BASE_URL}/history/${sessionId}/${analysisId}`);
  return handleResponse<AnalysisResponse>(res);
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`);
  return handleResponse<HealthResponse>(res);
}
