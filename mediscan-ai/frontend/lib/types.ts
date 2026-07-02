// Shared TypeScript types — mirrors backend/app/schemas/response.py exactly.
// Keeping these in sync by hand is intentional for a capstone: it's a small
// enough surface that a generated OpenAPI client would be overkill.

export type FindingSeverity = "normal" | "abnormal" | "critical";

export interface ClinicalFinding {
  parameter: string;
  value: string;
  reference_range: string | null;
  severity: FindingSeverity;
  plain_language_explanation: string;
}

export interface AnalysisResponse {
  analysis_id: string;
  session_id: string;
  file_name: string;
  summary: string;
  findings: ClinicalFinding[];
  overall_severity: FindingSeverity;
  recommended_action: string;
  disclaimer: string;
  provider_used: string;
  created_at: string;
}

export interface ChatResponse {
  analysis_id: string;
  question: string;
  answer: string;
  provider_used: string;
}

export interface AnalysisHistoryItem {
  analysis_id: string;
  file_name: string;
  overall_severity: FindingSeverity;
  summary: string;
  created_at: string;
}

export interface SessionHistoryResponse {
  session_id: string;
  analyses: AnalysisHistoryItem[];
}

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  gemini_configured: boolean;
  openrouter_configured: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.status = status;
    this.details = body.details;
  }
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
