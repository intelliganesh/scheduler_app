export default function DataTable({ columns, rows, empty = "No records found." }) {
  if (!rows.length) return <div className="empty-state"><span className="empty-icon">∅</span><strong>{empty}</strong><p>There is nothing to display here yet.</p></div>;
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id ?? index}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : row[column.key] ?? "—"}</td>)}</tr>)}</tbody></table></div>;
}
