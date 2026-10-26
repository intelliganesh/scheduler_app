import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatUtcInKolkata } from "../utils/dateTime";

export default function DashboardPage({ token, menus = [], onNavigate }) {
  const [data, setData] = useState(null); const [error, setError] = useState("");
  useEffect(() => { api.dashboard(token).then(setData).catch((err) => setError(err.message)); }, [token]);
  if (error) return <div className="card error-state"><strong>Unable to load dashboard</strong><p>{error}</p></div>;
  if (!data) return <div className="loading-state">Loading dashboard…</div>;
  const stats = [["Total Jobs", data.total_jobs, "dashboard"], ["Scheduled Jobs", data.active_scheduled_jobs, "scheduled_jobs"], ["Completed Runs", data.completed_runs, "task_management"], ["Failed Runs", data.failed_runs, "task_management"], ["Generated Files", data.generated_files, "generated_files"]];
  const statCard = ([label, value, icon]) => { const content = <><span className="stat-icon">{icon === "dashboard" ? "▦" : icon === "scheduled_jobs" ? "◷" : icon === "generated_files" ? "⇩" : "✓"}</span><span className="stat-label">{label}</span><strong>{value}</strong></>; return menus.includes(icon) ? <button className="stat-card" key={label} onClick={() => onNavigate(icon)}>{content}</button> : <div className="stat-card" key={label}>{content}</div>; };
  return <><div className="welcome-row"><div><p className="eyebrow">Overview</p><h2>Dashboard overview</h2><p className="muted">Monitor report jobs and recent activity from one place.</p></div>{menus.includes("create_job") && <button onClick={() => onNavigate("create_job")}>＋ Create Job</button>}</div><div className="stat-grid">{stats.map(statCard)}</div><section className="card"><div className="section-heading"><div><p className="eyebrow">Activity</p><h3>Recent executions</h3></div>{menus.includes("task_management") && <button className="text-button" onClick={() => onNavigate("task_management")}>View all</button>}</div><DataTable empty="No executions yet." columns={[{ key: "job_id", label: "Job" }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "current_step", label: "Step" }, { key: "started_at", label: "Started", render: (row) => formatUtcInKolkata(row.started_at) }]} rows={data.recent_runs || []} /></section></>;
}
