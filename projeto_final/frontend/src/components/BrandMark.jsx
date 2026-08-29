import { Goal } from "lucide-react";

export default function BrandMark({ compact = false }) {
  return (
    <div className={`brand-mark ${compact ? "brand-mark-compact" : ""}`} aria-label="Football Intelligence Platform">
      <span className="brand-mark-icon" aria-hidden="true">
        <Goal size={compact ? 28 : 34} strokeWidth={1.8} />
      </span>
      {compact ? null : (
        <span className="brand-mark-copy">
          <strong>Football</strong>
          <small>Intelligence</small>
        </span>
      )}
    </div>
  );
}
