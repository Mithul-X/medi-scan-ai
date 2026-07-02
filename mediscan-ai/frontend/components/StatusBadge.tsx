import { FindingSeverity } from "@/lib/types";

const SEVERITY_CONFIG: Record<
  FindingSeverity,
  { label: string; className: string }
> = {
  normal: { label: "Normal", className: "badge badge-normal" },
  abnormal: { label: "Abnormal", className: "badge badge-abnormal" },
  critical: { label: "Critical", className: "badge badge-critical" },
};

export default function StatusBadge({
  severity,
}: {
  severity: FindingSeverity;
}) {
  const config = SEVERITY_CONFIG[severity];
  return <span className={config.className}>{config.label}</span>;
}
