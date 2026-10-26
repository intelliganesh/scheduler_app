export default function StatusBadge({ status }) {
  const value = status || "Pending";
  return <span className={`status status-${value.toLowerCase().replaceAll(" ", "-")}`}>{value}</span>;
}
