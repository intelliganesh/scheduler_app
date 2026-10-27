import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatUtcInKolkata } from "../utils/dateTime";

export default function DashboardPage({ token, menus = [], onNavigate }) {
  const [data, setData] = useState(null); const [jobs, setJobs] = useState([]); const [error, setError] = useState("");
  useEffect(() => { Promise.all([api.dashboard(token), menus.includes("jobs") ? api.jobs(token) : Promise.resolve([])]).then(([dashboard, jobList]) => { setData(dashboard); setJobs(jobList); }).catch((err) => setError(err.message)); }, [token, menus]);
  if (error) return <div className="card error-state"><strong>Unable to load dashboard</strong><p>{error}</p></div>;
  if (!data) return <div className="loading-state">Loading dashboard…</div>;
  const stats = [["Total Jobs", data.total_jobs, "jobs"], ["Scheduled Jobs", data.active_scheduled_jobs, "jobs"], ["Completed Runs", data.completed_runs, "jobs"], ["Failed Runs", data.failed_runs, "jobs"], ["Generated Files", data.generated_files, "generated_files"]];
  const statCard = ([label, value, icon]) => { const content = <><span className="stat-icon">{icon === "generated_files" ? "⇩" : icon === "jobs" ? "◷" : "✓"}</span><span className="stat-label">{label}</span><strong>{value}</strong></>; return menus.includes(icon) ? <button className="stat-card" key={label} onClick={() => onNavigate(icon)}>{content}</button> : <div className="stat-card" key={label}>{content}</div>; };
  const jobName = (id) => jobs.find((job) => job.id === id)?.title || `Job #${id}`;
  const displayStep = (step) => step === "Completed" ? "Report generated" : step || "—";
  return <><div className="welcome-row dashboard-actions">{menus.includes("jobs") && <button onClick={() => onNavigate("jobs")}>＋ New Job</button>}</div><div className="stat-grid">{stats.map(statCard)}</div><section className="card"><div className="section-heading"><h3>Recent executions</h3>{menus.includes("jobs") && <button className="text-button" onClick={() => onNavigate("jobs")}>View all</button>}</div><DataTable empty="No executions yet." columns={[{ key: "job_id", label: "Job Name", render: (row) => jobName(row.job_id) }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "current_step", label: "Last Step", render: (row) => displayStep(row.current_step) }, { key: "started_at", label: "Started", render: (row) => formatUtcInKolkata(row.started_at) }]} rows={data.recent_runs || []} /></section></>;
}
