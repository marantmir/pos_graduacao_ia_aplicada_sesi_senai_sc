export default function ConfidenceBadge({ level }) {
  const normalized = String(level || "Medio").toLowerCase();
  const className = normalized.includes("alto")
    ? "badge badge-high"
    : normalized.includes("baixo")
      ? "badge badge-low"
      : "badge badge-medium";

  return <span className={className}>{level || "Medio"}</span>;
}
