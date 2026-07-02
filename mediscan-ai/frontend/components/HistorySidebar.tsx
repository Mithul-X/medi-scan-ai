import { AnalysisHistoryItem } from "@/lib/types";
import StatusBadge from "./StatusBadge";

interface HistorySidebarProps {
  items: AnalysisHistoryItem[];
  activeAnalysisId?: string;
  onSelect: (analysisId: string) => void;
}

export default function HistorySidebar({
  items,
  activeAnalysisId,
  onSelect,
}: HistorySidebarProps) {
  return (
    <aside className="history-sidebar">
      <h2 className="history-title">Recent</h2>
      {items.length === 0 ? (
        <p className="history-empty">No analyses yet this session.</p>
      ) : (
        <ul className="history-list">
          {items.map((item) => (
            <li key={item.analysis_id}>
              <button
                className={`history-item ${
                  item.analysis_id === activeAnalysisId
                    ? "history-item-active"
                    : ""
                }`}
                onClick={() => onSelect(item.analysis_id)}
              >
                <span className="history-item-name">{item.file_name}</span>
                <StatusBadge severity={item.overall_severity} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="history-note">Last 3 analyses are kept per session.</p>
    </aside>
  );
}
