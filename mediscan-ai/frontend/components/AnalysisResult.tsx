import { AnalysisResponse } from "@/lib/types";
import StatusBadge from "./StatusBadge";

export default function AnalysisResult({
  result,
}: {
  result: AnalysisResponse;
}) {
  return (
    <div className="result-panel">
      <div className="result-header">
        <div>
          <p className="result-filename">{result.file_name}</p>
          <p className="result-provider">via {formatProvider(result.provider_used)}</p>
        </div>
        <StatusBadge severity={result.overall_severity} />
      </div>

      <section className="result-section">
        <h2 className="result-section-title">Summary</h2>
        <p className="result-summary">{result.summary}</p>
      </section>

      {result.findings.length > 0 && (
        <section className="result-section">
          <h2 className="result-section-title">Findings</h2>
          <div className="findings-list">
            {result.findings.map((finding, i) => (
              <div key={i} className="finding-card">
                <div className="finding-header">
                  <span className="finding-parameter">{finding.parameter}</span>
                  <StatusBadge severity={finding.severity} />
                </div>
                <div className="finding-values">
                  <span className="finding-value">{finding.value}</span>
                  {finding.reference_range && (
                    <span className="finding-range">
                      ref: {finding.reference_range}
                    </span>
                  )}
                </div>
                <p className="finding-explanation">
                  {finding.plain_language_explanation}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="result-section">
        <h2 className="result-section-title">Recommended action</h2>
        <p className="result-action">{result.recommended_action}</p>
      </section>

      <p className="result-disclaimer">{result.disclaimer}</p>
    </div>
  );
}

function formatProvider(provider: string): string {
  if (provider === "gemini") return "Gemini 2.5 Flash";
  if (provider.startsWith("openrouter:")) {
    const model = provider.split(":").slice(1).join(":");
    return `OpenRouter (${model})`;
  }
  return provider;
}
