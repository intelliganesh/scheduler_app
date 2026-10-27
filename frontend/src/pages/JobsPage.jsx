import { useEffect, useMemo, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatKolkata, formatUtcInKolkata } from "../utils/dateTime";

const STATUS_FILTERS = ["All", "Scheduled", "Running", "Completed", "Failed"];

function latestStatus(job) {
  if (job.last_run_status) return job.last_run_status;
  return job.enabled ? "Scheduled" : "Disabled";
}

function delimiterLabel(value) {
  return ({ ",": "Comma (,)", "|": "Pipe (|)", ";": "Semicolon (;)", "\t": "Tab (\\t)" }[value] || "Comma (,)");
}
function scheduleTypeLabel(value) {
  return ({ one_time: "One Time", hourly_1: "Every 1 Hour", hourly_2: "Every 2 Hours", hourly_4: "Every 4 Hours", daily: "Daily", weekly: "Weekly", monthly: "Monthly" }[value] || "One Time");
}

export default function JobsPage({ token, onNavigate }) {
  const [jobs, setJobs] = useState([]); const [companies, setCompanies] = useState([]); const [runs, setRuns] = useState([]);
  const [query, setQuery] = useState(""); const [status, setStatus] = useState("All"); const [error, setError] = useState("");
  const [selectedJob, setSelectedJob] = useState(null); const [busy, setBusy] = useState("");
  const companyName = (id) => companies.find((company) => company.id === id)?.company_name || `Company ${id}`;
  const jobCompanyNames = (job) => {
    const selectedIds = Object.keys(job.client_selections || {}).map(Number).filter(Number.isFinite);
    const ids = selectedIds.length ? selectedIds : [job.company_id];
    return ids.map(companyName).join(", ");
  };
  async function load() {
    try { const [jobList, companyList, runList] = await Promise.all([api.jobs(token), api.companies(token), api.runs(token)]); setJobs(jobList); setCompanies(companyList); setRuns(runList); setError(""); }
    catch (err) { setError(err.message); }
  }
  useEffect(() => { if (token) load(); }, [token]);
  const filtered = useMemo(() => jobs.filter((job) => {
    const matchesQuery = `${job.title} ${job.source_key} ${jobCompanyNames(job)}`.toLowerCase().includes(query.toLowerCase());
    const current = latestStatus(job).toLowerCase();
    return matchesQuery && (status === "All" || current === status.toLowerCase() || (status === "Failed" && current.includes("failed")));
  }), [jobs, companies, query, status]);
  const selectedRuns = selectedJob ? runs.filter((run) => run.job_id === selectedJob.id) : [];
  async function runNow(job) { if (!window.confirm(`Run “${job.title}” now?`)) return; try { setBusy(`run-${job.id}`); await api.runJob(token, job.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }
  async function toggle(job) { try { setBusy(`toggle-${job.id}`); await api.toggleJob(token, job.id, !job.enabled); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }
  async function retry(run) { if (!window.confirm("Retry this failed execution?")) return; try { setBusy(`retry-${run.id}`); await api.retryRun(token, run.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }
  return <>
    <div className="page-intro jobs-page-intro"><button onClick={() => onNavigate?.("jobs_new")}>＋ New Job</button></div>
    {error && <div className="inline-error">{error}</div>}
    <section className="card jobs-card"><div className="jobs-toolbar"><div><h3>All jobs</h3></div><div className="jobs-toolbar-actions"><input className="search-input" placeholder="Search jobs…" value={query} onChange={(event) => setQuery(event.target.value)} /><span className="jobs-count">{filtered.length} {filtered.length === 1 ? "job" : "jobs"}</span></div></div><div className="status-filter-row"><span className="filter-label">Status</span><div className="status-filters">{STATUS_FILTERS.map((item) => <button key={item} className={status === item ? "filter-active" : "small-button secondary"} onClick={() => setStatus(item)}>{item}</button>)}</div></div>
      <DataTable empty="No jobs match the selected filters." columns={[{ key: "title", label: "Job Name" }, { key: "company_id", label: "Company / Clients", render: (row) => jobCompanyNames(row) }, { key: "source_key", label: "Stored Procedure" }, { key: "next_run_at", label: "Scheduled Date", render: (row) => row.next_run_at || row.schedule_at ? formatKolkata(row.next_run_at || row.schedule_at) : "—" }, { key: "schedule_type", label: "Schedule Type", render: (row) => scheduleTypeLabel(row.schedule_type) }, { key: "status", label: "Status", render: (row) => <StatusBadge status={latestStatus(row)} /> }, { key: "actions", label: "Actions", render: (row) => <div className="row-actions"><button className="small-button secondary" onClick={() => setSelectedJob(row)}>View details</button><button className="small-button" disabled={busy === `run-${row.id}`} onClick={() => runNow(row)}>Run now</button><button className="small-button secondary" disabled={busy === `toggle-${row.id}`} onClick={() => toggle(row)}>{row.enabled ? "Disable" : "Enable"}</button></div> }]} rows={filtered} />
    </section>
    {selectedJob && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedJob(null); }}><div className="modal-panel details-panel" role="dialog" aria-modal="true"><div className="modal-header"><div><p className="eyebrow">Job details</p><h3>{selectedJob.title}</h3></div><button className="icon-button" onClick={() => setSelectedJob(null)} aria-label="Close">×</button></div><dl className="job-details"><dt>Company / Clients</dt><dd>{jobCompanyNames(selectedJob)}</dd><dt>Stored Procedure</dt><dd>{selectedJob.source_key}</dd><dt>Schedule Type</dt><dd>{scheduleTypeLabel(selectedJob.schedule_type)}</dd><dt>CSV Delimiter</dt><dd>{delimiterLabel(selectedJob.delimiter)}</dd><dt>Export Split By</dt><dd>{selectedJob.export_split_by === "client_id" ? "Client ID" : selectedJob.export_split_by === "pay_date" ? "Pay Date" : "File Name (single CSV)"}</dd><dt>Next Execution</dt><dd>{selectedJob.next_run_at ? formatKolkata(selectedJob.next_run_at) : "Completed"}</dd><dt>Enabled</dt><dd>{selectedJob.enabled ? "Yes" : "No"}</dd><dt>Latest Status</dt><dd><StatusBadge status={latestStatus(selectedJob)} /></dd></dl><h4>Execution History</h4><DataTable empty="No executions yet." columns={[{ key: "started_at", label: "Execution Date", render: (row) => formatUtcInKolkata(row.started_at) }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "current_step", label: "Current / Failed Step" }, { key: "error_message", label: "Error Details", render: (row) => row.error_message || "—" }, { key: "retry", label: "Retry", render: (row) => ["Failed", "Partially Completed"].includes(row.status) ? <button className="small-button" disabled={busy === `retry-${row.id}`} onClick={() => retry(row)}>Retry</button> : "—" }]} rows={selectedRuns} /></div></div>}
  </>;
}
