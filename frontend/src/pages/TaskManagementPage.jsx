import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatUtcInKolkata } from "../utils/dateTime";

export default function TaskManagementPage({ token }) {
  const [runs, setRuns] = useState([]); const [jobs, setJobs] = useState([]); const [error, setError] = useState("");
  const load = () => Promise.all([api.runs(token), api.jobs(token)]).then(([runList, jobList]) => { setRuns(runList); setJobs(jobList); }).catch((err) => setError(err.message));
  useEffect(() => { load(); }, [token]); const jobName = (id) => jobs.find((job) => job.id === id)?.title || `Job #${id}`;
  async function retry(id) { try { await api.retryRun(token, id); await load(); } catch (err) { setError(err.message); } }
  return <><div className="page-intro"><div><p className="eyebrow">Operations</p><h2>Task management</h2><p className="muted">Review execution history and recover failed jobs.</p></div></div>{error && <div className="inline-error">{error}</div>}<section className="card"><DataTable empty="No task executions yet." columns={[{ key: "job_id", label: "Job Name", render: (row) => jobName(row.job_id) }, { key: "started_at", label: "Execution Date", render: (row) => formatUtcInKolkata(row.started_at) }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "current_step", label: "Current / Failed Step" }, { key: "error_message", label: "Details", render: (row) => row.error_message || "—" }, { key: "actions", label: "Actions", render: (row) => ["Failed", "Partially Completed"].includes(row.status) ? <button className="small-button" onClick={() => retry(row.id)}>Retry</button> : "—" }]} rows={runs} /></section></>;
}
