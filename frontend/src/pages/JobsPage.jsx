import { useEffect, useMemo, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatKolkata, formatUtcInKolkata } from "../utils/dateTime";
import ConfirmDialog from "../components/ConfirmDialog";

function latestStatus(job) {
  if (!job.enabled) return "Disabled";
  return job.last_run_status || "Scheduled";
}

function delimiterLabel(value) {
  return ({ ",": "Comma (,)", "|": "Pipe (|)", ";": "Semicolon (;)", "\t": "Tab (\\t)" }[value] || "Comma (,)");
}
function scheduleTypeLabel(value) {
  return ({ one_time: "One Time", every_1_minute: "Every 1 Minute", every_2_minutes: "Every 2 Minutes", hourly_1: "Every 1 Hour", hourly_2: "Every 2 Hours", hourly_4: "Every 4 Hours", daily: "Daily", weekly: "Weekly", monthly: "Monthly" }[value] || "One Time");
}
function exportSplitLabel(value) {
  return ({ file_name: "File Name", client_id: "Client ID", pay_date: "Pay Date", file_client: "File Name + Client ID", file_pay: "File Name + Pay Date", client_pay: "Client ID + Pay Date", file_client_pay: "File Name + Client ID + Pay Date" }[value] || "File Name");
}

export default function JobsPage({ token, onNavigate, onEdit, onViewDetails }) {
  const [jobs, setJobs] = useState([]); const [companies, setCompanies] = useState([]); const [runs, setRuns] = useState([]); const [files, setFiles] = useState([]);
  const [selectedJobIds, setSelectedJobIds] = useState([]);
  const [refreshing, setRefreshing] = useState(true);
  const [query, setQuery] = useState(""); const [error, setError] = useState("");
  const [busy, setBusy] = useState(""); const [confirmation, setConfirmation] = useState(null);
  const companyName = (id) => companies.find((company) => company.id === id)?.company_name || `Company ${id}`;
  const jobCompanyNames = (job) => {
    const selectedIds = Object.keys(job.client_selections || {}).map(Number).filter(Number.isFinite);
    const ids = selectedIds.length ? selectedIds : [job.company_id];
    return ids.map(companyName).join(", ");
  };
  async function load() {
    try {
      setRefreshing(true);
      const [jobList, companyList, runList] = await Promise.all([api.jobs(token), api.companies(token), api.runs(token)]);
      const fileList = await api.files(token).catch(() => []);
      setJobs(jobList); setCompanies(companyList); setRuns(runList); setFiles(fileList); setError("");
    }
    catch (err) { setError(err.message); } finally { setRefreshing(false); }
  }
  useEffect(() => { if (token) load(); }, [token]);
  useEffect(() => { setSelectedJobIds((current) => current.filter((id) => jobs.some((job) => job.id === id))); }, [jobs]);
  const filtered = useMemo(() => jobs.filter((job) => {
    const matchesQuery = `${job.title} ${job.source_key} ${jobCompanyNames(job)}`.toLowerCase().includes(query.toLowerCase());
    return matchesQuery;
  }), [jobs, companies, query]);
  function latestFile(jobId) { return files.find((file) => file.job_id === jobId); }
  function baseFileName(fileName) { return fileName.replace(/\.[^.]+$/, ""); }
  function scheduleParts(job) {
    const value = job.schedule_at || job.next_run_at;
    if (!value) return { date: "—", time: "—", day: "—" };
    const text = String(value); const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text); const date = new Date(hasZone ? text : `${text}+05:30`);
    if (Number.isNaN(date.getTime())) return { date: "—", time: "—", day: "—" };
    const parts = (options) => new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Kolkata", ...options }).format(date);
    return { date: parts({ month: "2-digit", day: "2-digit", year: "numeric" }), time: parts({ timeStyle: "short" }), day: parts({ weekday: "long" }) };
  }
  function askConfirmation(message, action, confirmLabel = "Confirm") { setConfirmation({ message, action, confirmLabel }); }
  async function runNow(job) { askConfirmation(`Run “${job.title}” now?`, async () => { try { setBusy(`run-${job.id}`); await api.runJob(token, job.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }, "Run now"); }
  async function runSelected() {
    const selected = filtered.filter((job) => selectedJobIds.includes(job.id) && job.enabled);
    if (!selected.length) return;
    askConfirmation(`Run ${selected.length} selected ${selected.length === 1 ? "job" : "jobs"} now?`, async () => {
    // Reload even after a failure so statuses reflect the failed run, then show the reason.
    let failure = "";
    try {
      setBusy("run-selected");
      for (const job of selected) await api.runJob(token, job.id);
      setSelectedJobIds([]);
    } catch (err) { failure = err.message; } finally { setBusy(""); await load(); if (failure) setError(failure); }
    }, "Run selected");
  }
  async function toggle(job) { try { setBusy(`toggle-${job.id}`); await api.toggleJob(token, job.id, !job.enabled); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }
  async function retry(run) { askConfirmation("Retry this failed execution?", async () => { try { setBusy(`retry-${run.id}`); await api.retryRun(token, run.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }, "Retry"); }
  return <>
    <div className="page-intro jobs-page-intro"><button onClick={() => onNavigate?.("jobs_new")}>＋ New Job</button></div>
    {error && <div className="inline-error">{error}</div>}
    <section className="card jobs-card"><div className="jobs-toolbar"><div><h3>All jobs ({filtered.length})</h3></div><div className="jobs-toolbar-actions"><button type="button" className="icon-button" title="Refresh jobs" aria-label="Refresh jobs" disabled={refreshing} onClick={load}>{refreshing ? <span className="refresh-spinner" aria-hidden="true">⟳</span> : <svg className="refresh-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-3.9L3 9m0 0V4m0 5h5M4 13a8 8 0 0 0 14.9 3.9L21 15m0 0v5m0-5h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg> }</button><button className="small-button" disabled={!selectedJobIds.length || busy === "run-selected"} onClick={runSelected}>{busy === "run-selected" ? "Running…" : `Run ${selectedJobIds.length ? ` (${selectedJobIds.length})` : ""}`}</button><a className="small-button secondary template-download-button" href="/mapped_payroll_columns_HDT.xlsx" download><span aria-hidden="true">↓</span> Download template</a><input className="search-input" placeholder="Search jobs…" value={query} onChange={(event) => setQuery(event.target.value)} /></div></div>
      <DataTable loading={refreshing && !jobs.length} empty="No jobs match the selected filters." columns={[{ key: "select", label: <input type="checkbox" aria-label="Select all enabled visible jobs" checked={filtered.some((job) => job.enabled) && filtered.filter((job) => job.enabled).every((job) => selectedJobIds.includes(job.id))} onChange={(event) => setSelectedJobIds(event.target.checked ? filtered.filter((job) => job.enabled).map((job) => job.id) : [])} />, render: (row) => <input type="checkbox" aria-label={`Select ${row.title}`} disabled={!row.enabled} checked={selectedJobIds.includes(row.id)} onChange={(event) => setSelectedJobIds((current) => event.target.checked ? [...new Set([...current, row.id])] : current.filter((id) => id !== row.id))} /> }, { key: "title", label: "Job Name", render: (row) => <span className="job-name" title={row.title}>{row.title}</span> }, { key: "file_name", label: "File Name", render: (row) => { const fileName = latestFile(row.id)?.file_name; const displayedName = fileName ? baseFileName(fileName) : ""; return fileName ? <span className="file-name" title={displayedName}>{displayedName}</span> : "—"; } }, { key: "last_updated", label: "Last Created / Updated", render: (row) => { const file = latestFile(row.id); const timestamps = [file?.created_at, row.updated_at, row.created_at].filter(Boolean); const latest = timestamps.reduce((current, value) => new Date(value) > new Date(current) ? value : current, null); return latest ? formatUtcInKolkata(latest) : "—"; } }, { key: "day", label: "Day", render: (row) => scheduleParts(row).day }, { key: "start_time", label: "Time", render: (row) => scheduleParts(row).time }, { key: "status", label: "Status", render: (row) => <StatusBadge status={latestStatus(row)} /> }, { key: "actions", label: "Actions", render: (row) => <button className="small-button secondary" onClick={() => onEdit?.(row)}>Edit</button> }]} rows={filtered} />
    </section>
    <ConfirmDialog open={Boolean(confirmation)} title="Confirm action" message={confirmation?.message} confirmLabel={confirmation?.confirmLabel} onCancel={() => setConfirmation(null)} onConfirm={async () => { const action = confirmation?.action; setConfirmation(null); await action?.(); }} />
  </>;
}
