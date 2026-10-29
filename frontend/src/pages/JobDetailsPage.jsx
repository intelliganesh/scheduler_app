import { useEffect, useMemo, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import ConfirmDialog from "../components/ConfirmDialog";
import { api } from "../services/api";
import { formatKolkata, formatUtcInKolkata } from "../utils/dateTime";

const PAGE_SIZE = 10;
const scheduleLabels = { one_time: "One Time", every_1_minute: "Every 1 Minute", every_2_minutes: "Every 2 Minutes", hourly_1: "Every 1 Hour", hourly_2: "Every 2 Hours", hourly_4: "Every 4 Hours", daily: "Daily", weekly: "Weekly", monthly: "Monthly" };
const splitLabels = { file_name: "File Name", client_id: "Client ID", pay_date: "Pay Date", file_client: "File Name + Client ID", file_pay: "File Name + Pay Date", client_pay: "Client ID + Pay Date", file_client_pay: "File Name + Client ID + Pay Date" };

function Pager({ page, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (pages <= 1) return null;
  return <div className="pagination"><span>Page {page} of {pages}</span><div><button className="small-button secondary" disabled={page === 1} onClick={() => onChange(page - 1)}>Previous</button><button className="small-button secondary" disabled={page === pages} onClick={() => onChange(page + 1)}>Next</button></div></div>;
}

export default function JobDetailsPage({ token, job, onBack }) {
  const [companies, setCompanies] = useState([]); const [runs, setRuns] = useState([]); const [files, setFiles] = useState([]);
  const [filesPage, setFilesPage] = useState(1); const [runsPage, setRunsPage] = useState(1); const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [confirmation, setConfirmation] = useState(null);
  async function load() {
    try { setError(""); const [companyList, runList, fileList] = await Promise.all([api.companies(token), api.runs(token), api.files(token)]); setCompanies(companyList); setRuns(runList.filter((run) => run.job_id === job.id)); setFiles(fileList.filter((file) => file.job_id === job.id)); }
    catch (err) { setError(err.message); }
  }
  useEffect(() => { if (token && job) load(); }, [token, job?.id]);
  const companyName = (id) => companies.find((company) => String(company.id) === String(id))?.company_name || `Company ${id}`;
  const clients = Object.keys(job?.client_selections || {}).map(Number).filter(Number.isFinite);
  const clientNames = (clients.length ? clients : [job?.company_id]).filter(Boolean).map(companyName).join(", ");
  const latestStatus = job?.enabled === false ? "Disabled" : job?.last_run_status || "Scheduled";
  const fileRows = useMemo(() => files.slice((filesPage - 1) * PAGE_SIZE, filesPage * PAGE_SIZE), [files, filesPage]);
  const runRows = useMemo(() => runs.slice((runsPage - 1) * PAGE_SIZE, runsPage * PAGE_SIZE), [runs, runsPage]);
  async function download(file) { try { await api.downloadFile(token, file.id, file.file_name); } catch (err) { setError(err.message); } }
  function retry(run) { setConfirmation({ message: "Retry this failed execution?", action: async () => { try { setBusy(`retry-${run.id}`); await api.retryRun(token, run.id); await load(); } catch (err) { setError(err.message); } finally { setBusy(""); } }, confirmLabel: "Retry" }); }
  if (!job) return <section className="card"><p className="inline-error">Job details are unavailable.</p><button className="small-button secondary" onClick={onBack}>Back to Jobs</button></section>;
  return <div className="job-details-page"><div className="page-intro"><div><p className="eyebrow">Jobs</p><h2>{job.title}</h2><p className="muted">Review configuration, generated files, and execution history.</p></div><button className="small-button secondary" onClick={onBack}>Back to Jobs</button></div>{error && <div className="inline-error">{error}</div>}<section className="card job-summary-card"><div className="job-details-grid"><div><span>Company / Clients</span><strong>{clientNames || "—"}</strong></div><div><span>Stored Procedure</span><strong>{job.source_key || "—"}</strong></div><div><span>Schedule Type</span><strong>{scheduleLabels[job.schedule_type] || "One Time"}</strong></div><div><span>Next Execution</span><strong>{job.next_run_at ? formatKolkata(job.next_run_at) : "Completed"}</strong></div><div><span>Export Split By</span><strong>{splitLabels[job.export_split_by] || "File Name"}</strong></div><div><span>Status</span><strong><StatusBadge status={latestStatus} /></strong></div></div></section><section className="card details-table-card"><div className="section-heading"><div><p className="eyebrow">Reports</p><h3>Generated Files</h3></div><span className="table-count">{files.length} file{files.length === 1 ? "" : "s"}</span></div><DataTable empty="No generated files for this job yet." columns={[{ key: "file_name", label: "File Name" }, { key: "created_at", label: "Created", render: (row) => formatUtcInKolkata(row.created_at) }, { key: "row_count", label: "Rows" }, { key: "download", label: "Download", render: (row) => <button className="small-button" onClick={() => download(row)}>Download</button> }]} rows={fileRows} /><Pager page={filesPage} total={files.length} onChange={setFilesPage} /></section><section className="card details-table-card"><div className="section-heading"><div><p className="eyebrow">Monitoring</p><h3>Execution History</h3></div><span className="table-count">{runs.length} run{runs.length === 1 ? "" : "s"}</span></div><DataTable empty="No executions yet." columns={[{ key: "started_at", label: "Execution Date", render: (row) => formatUtcInKolkata(row.started_at) }, { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> }, { key: "current_step", label: "Current / Failed Step" }, { key: "error_message", label: "Error Details", render: (row) => row.error_message || "—" }, { key: "retry", label: "Retry", render: (row) => ["Failed", "Partially Completed"].includes(row.status) ? <button className="small-button" disabled={busy === `retry-${row.id}`} onClick={() => retry(row)}>Retry</button> : "—" }]} rows={runRows} /><Pager page={runsPage} total={runs.length} onChange={setRunsPage} /></section><ConfirmDialog open={Boolean(confirmation)} title="Confirm action" message={confirmation?.message} confirmLabel={confirmation?.confirmLabel} onCancel={() => setConfirmation(null)} onConfirm={async () => { const action = confirmation?.action; setConfirmation(null); await action?.(); }} /></div>;
}
