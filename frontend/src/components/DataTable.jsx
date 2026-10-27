import emptyStateImage from "../assets/empty-state.svg";

export default function DataTable({ columns, rows, empty = "No records found.", loading = false }) {
  if (loading) return <div className="table-wrap table-skeleton" aria-label="Loading data" aria-busy="true"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{Array.from({ length: 4 }, (_, index) => <tr key={index}>{columns.map((column) => <td key={column.key}><span className="skeleton-line" /></td>)}</tr>)}</tbody></table></div>;
  if (!rows.length) return <div className="empty-state"><img src={emptyStateImage} alt="" /><strong>No data available</strong></div>;
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id ?? index}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : row[column.key] ?? "—"}</td>)}</tr>)}</tbody></table></div>;
}
