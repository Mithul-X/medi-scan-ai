"use client";

import { useCallback, useEffect, useState } from "react";
import FileUpload from "@/components/FileUpload";
import AnalysisResult from "@/components/AnalysisResult";
import HistorySidebar from "@/components/HistorySidebar";
import ChatPanel from "@/components/ChatPanel";
import { getHistory, getHistoryAnalysis, uploadAndAnalyze } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import { AnalysisHistoryItem, AnalysisResponse, ApiError } from "@/lib/types";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSessionId(getSessionId());
  }, []);

  const refreshHistory = useCallback(async (sid: string) => {
    try {
      const data = await getHistory(sid);
      setHistory(data.analyses);
    } catch {
      // History is a convenience feature — a failed fetch shouldn't block the
      // main upload/analyze flow, so we swallow this rather than surfacing it.
    }
  }, []);

  useEffect(() => {
    if (sessionId) refreshHistory(sessionId);
  }, [sessionId, refreshHistory]);

  async function handleSelectHistory(analysisId: string) {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const analysis = await getHistoryAnalysis(sessionId, analysisId);
      setResult(analysis);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not load that analysis. It may have been pruned from history.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleUpload(file: File) {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const analysis = await uploadAndAnalyze(file, sessionId);
      setResult(analysis);
      refreshHistory(sessionId);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not analyze that file. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page">
      <header className="page-header">
        <h1 className="page-title">MediScan AI</h1>
        <p className="page-subtitle">
          Upload a lab report, scan, or prescription &mdash; get a plain-language
          explanation of what it means.
        </p>
      </header>

      <div className="page-layout">
        <HistorySidebar
          items={history}
          activeAnalysisId={result?.analysis_id}
          onSelect={handleSelectHistory}
        />

        <div className="page-main">
          <FileUpload onUpload={handleUpload} isLoading={isLoading} />

          {error && <p className="page-error">{error}</p>}

          {result && (
            <>
              <AnalysisResult result={result} />
              <ChatPanel analysisId={result.analysis_id} sessionId={sessionId ?? ""} />
            </>
          )}
        </div>
      </div>

      <footer className="page-footer">
        <p>
          MediScan AI does not provide medical advice. Always consult a
          qualified healthcare professional.
        </p>
      </footer>
    </main>
  );
}
