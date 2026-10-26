import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import StatusBadge from "../components/StatusBadge";
import { api } from "../services/api";
import { formatKolkata } from "../utils/dateTime";

export default function ScheduledJobsPage({ token, onNavigate }) {
  const [jobs, setJobs] = useState([]); const [companies, setCompanies] = useState([]); const [query, setQuery] = useState(""); const [error, setError] = useState("");
  const load = () => Promise.all([api.jobs(token), api.companies(token)]).then(([jobList, companyList]) => { setJobs(jobList); setCompanies(companyList); }).catch((err) => setError(err.message));
  useEffect(() => { load(); }, [token]);
  const company = (id) => companies.find((item) => item.id === id)?.company_name || `Company ${id}`;
  const filtered = jobs.filter((job) => `${job.title} ${job.source_key} ${company(job.company_id)}`.toLowerCase().includes(query.toLowerCase()));
  async function run(id) { try { await api.runJob(token, id); await load(); } catch (err) { setError(err.message); } }
  async function toggle(job) { try { await api.toggleJob(token, job.id, !job.enabled); await load(); } catch (err) { setError(err.message); } }
  return <><div className="page-intro"><div><p className="eyebrow">Operations</p><h2>Scheduled jobs</h2><p className="muted">Manage one-time report schedules and run history.</p></div><button onClick={() => onNavigate("create_job")}>＋ Create Job</button></div>{error && <div className="inline-error">{error}</div>}<section className="card"><div className="toolbar"><input className="search-input" placeholder="Search jobs…" value={query} onChange={(event) => setQuery(event.target.value)} /><span className="muted">{filtered.length} jobs</span></div><DataTable empty="No scheduled jobs yet." columns={[{ key: "title", label: "Job Name" }, { key: "company_id", label: "Company", render: (row) => company(row.company_id) }, { key: "source_key", label: "Stored Procedure" }, { key: "next_run_at", label: "Scheduled", render: (row) => row.next_run_at ? formatKolkata(row.next_run_at) : "Completed" }, { key: "last_run_status", label: "Status", render: (row) => <StatusBadge status={row.last_run_status || (row.enabled ? "Scheduled" : "Disabled")} /> }, { key: "actions", label: "Actions", render: (row) => <div className="row-actions"><button className="small-button" onClick={() => run(row.id)}>Run now</button><button className="small-button secondary" onClick={() => toggle(row)}>{row.enabled ? "Disable" : "Enable"}</button></div> }]} rows={filtered} /></section></>;
}
