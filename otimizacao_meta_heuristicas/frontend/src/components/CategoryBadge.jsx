export default function CategoryBadge({ category }) {
  if (!category) return null;
  return <span className="badge badge-category">{category}</span>;
}
