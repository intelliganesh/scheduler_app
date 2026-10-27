import { useEffect, useState } from "react";
import { api } from "../services/api";

export default function DeletionCenterPage({ token }) {
  const [summary, setSummary] = useState(null); const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  async function load() { try { setError(""); setSummary(await api.deletionSummary(token)); } catch (err) { setError(err.message); } }
  useEffect(() => { if (token) load(); }, [token]);
  async function removeAll() {
    if (confirmation !== "DELETE ALL" || !window.confirm("Delete all application jobs, runs, generated files, and associated uploads? This cannot be undone.")) return;
    try { setBusy(true); setError(""); const result = await api.deleteAllJobsAndFiles(token); setMessage(`Deleted ${result.jobs} jobs, ${result.runs} runs, and ${result.generated_files} generated files.`); setConfirmation(""); await load(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <div className="deletion-center-page"><div className="page-intro"><div><p className="eyebrow">Administration</p><h2>Deletion Center</h2><p className="muted">Remove application-created jobs and generated report files from this local environment.</p></div></div>{error && <div className="inline-error">{error}</div>}{message && <div className="inline-success">{message}</div>}<section className="card deletion-card"><div className="deletion-warning"><strong>Destructive action</strong><span>This does not delete companies, employees, payroll data, users, permissions, or application configuration.</span></div><h3>Current application data</h3>{summary ? <div className="deletion-summary"><div><strong>{summary.jobs}</strong><span>Jobs</span></div><div><strong>{summary.runs}</strong><span>Execution runs</span></div><div><strong>{summary.generated_files}</strong><span>Generated files</span></div><div><strong>{summary.uploads}</strong><span>Uploaded lists</span></div></div> : <p className="loading-state">Loading counts…</p>}<label className="deletion-confirm">Type <strong>DELETE ALL</strong> to enable deletion<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="DELETE ALL" autoComplete="off" /></label><button className="danger-button" disabled={busy || confirmation !== "DELETE ALL"} onClick={removeAll}>{busy ? "Deleting…" : "Delete all jobs and files"}</button></section></div>;
}
