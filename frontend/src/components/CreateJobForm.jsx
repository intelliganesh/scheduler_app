import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";

const MAPPED_PROCEDURE = "mapped_employee_payroll_report";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function scheduleAtInKolkata(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || "");
  if (!match) throw new Error("Choose a valid schedule date and time.");
  const [, year, month, day, hour, minute] = match;
  const wallClock = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute)));
  if (Number.isNaN(wallClock.getTime()) || wallClock.getUTCFullYear() !== Number(year) || wallClock.getUTCMonth() + 1 !== Number(month) || wallClock.getUTCDate() !== Number(day) || Number(hour) > 23 || Number(minute) > 59) {
    throw new Error("Choose a valid schedule date and time.");
  }
  return `${value}:00+05:30`;
}

export default function CreateJobForm({ token, onCreated }) {
  const [companies, setCompanies] = useState([]); const [procedures, setProcedures] = useState([]);
  const [form, setForm] = useState({ title: "", schedule_at: "", company_id: "", recipients: [], source_key: "" });
  const [upload, setUpload] = useState(null); const [mappings, setMappings] = useState({}); const [draggedField, setDraggedField] = useState("");
  const [emailInput, setEmailInput] = useState(""); const [emailError, setEmailError] = useState("");
  const [message, setMessage] = useState(""); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const selectedProcedure = procedures.find((procedure) => procedure.key === form.source_key);
  const availableFields = selectedProcedure?.allowed_fields || []; const isMappingJob = form.source_key === MAPPED_PROCEDURE;
  const mappedCount = upload?.column_names?.filter((name) => mappings[name]).length || 0;
  const unmappedFields = useMemo(() => availableFields.filter((field) => !Object.values(mappings).includes(field)), [availableFields, mappings]);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.companies(token), api.approvedProcedures(token)]).then(([companyList, procedureList]) => {
      setCompanies(companyList); setProcedures(procedureList);
      setForm((current) => ({ ...current, company_id: current.company_id || String(companyList[0]?.id || ""), source_key: current.source_key || procedureList.find((item) => item.supports_mapping)?.key || procedureList[0]?.key || "" }));
    }).catch((err) => setError(err.message));
  }, [token]);
  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); }
  function addRecipients(rawValue) {
    const candidates = rawValue.split(",").map((value) => value.trim()).filter(Boolean);
    if (!candidates.length) return;
    const next = [...form.recipients]; const seen = new Set(next.map((email) => email.toLowerCase())); let problem = "";
    for (const email of candidates) {
      if (!EMAIL_PATTERN.test(email)) { problem = `Invalid email address: ${email}`; continue; }
      if (seen.has(email.toLowerCase())) { problem = `Email address already added: ${email}`; continue; }
      seen.add(email.toLowerCase()); next.push(email);
    }
    update("recipients", next); setEmailInput(""); setEmailError(problem);
  }
  function removeRecipient(email) { update("recipients", form.recipients.filter((item) => item !== email)); setEmailError(""); }
  function handleEmailKeyDown(event) { if (event.key === "Enter" || event.key === ",") { event.preventDefault(); addRecipients(emailInput); } }
  function handleEmailPaste(event) { const pasted = event.clipboardData.getData("text"); if (pasted.includes(",")) { event.preventDefault(); addRecipients(pasted); } }
  function setMapping(name, field) { setMappings((current) => ({ ...current, [name]: field || undefined })); }
  async function handleUpload(event) {
    const file = event.target.files?.[0]; if (!file) return; setError(""); setMessage("");
    try { const result = await api.uploadQuery(token, file); const names = typeof result.column_names === "string" ? JSON.parse(result.column_names) : result.column_names; setUpload({ id: result.id, original_name: result.original_name, column_names: names || [] }); setMappings({}); setMessage(`${names.length} TXT columns loaded. Map each one to an approved field.`); }
    catch (err) { event.target.value = ""; setError(err.message); }
  }
  function drop(name, event) { event.preventDefault(); if (draggedField) setMapping(name, draggedField); setDraggedField(""); }
  async function submit(event) {
    event.preventDefault(); setError(""); setMessage("");
    if (isMappingJob && (!upload || mappedCount !== upload.column_names.length)) { setError("Upload a TXT column list and map every column before scheduling."); return; }
    if (emailInput.trim()) { setEmailError("Press Enter or comma to add the typed email address."); return; }
    try { setSaving(true); const schedule_at = scheduleAtInKolkata(form.schedule_at); await api.createJob(token, { title: form.title, display_name: form.title, schedule_at, company_id: Number(form.company_id), source_type: "procedure", source_key: form.source_key, uploaded_query_id: upload?.id || null, column_mappings: isMappingJob ? upload.column_names.map((display_name) => ({ display_name, database_field: mappings[display_name] })) : null, recipients: form.recipients, enabled: true }); setMessage("Job created and scheduled."); setForm((current) => ({ ...current, title: "", schedule_at: "", recipients: [] })); setEmailInput(""); setEmailError(""); setUpload(null); setMappings({}); onCreated?.(); }
    catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  return <><div className="page-intro"><div><p className="eyebrow">Scheduling</p><h2>Create a report job</h2><p className="muted">Upload report columns, map them to approved payroll fields, and schedule one run.</p></div></div><section className="card"><form className="job-form" onSubmit={submit}>
    <label>Job Name <span className="required">*</span><input required value={form.title} onChange={(event) => update("title", event.target.value)} placeholder="e.g. Monthly payroll summary" /></label>
    <label>Schedule Date &amp; Time <span className="required">*</span><input required type="datetime-local" value={form.schedule_at} onInput={(event) => update("schedule_at", event.target.value)} onChange={(event) => update("schedule_at", event.target.value)} /></label>
    <label>Company <span className="required">*</span><select required value={form.company_id} onChange={(event) => update("company_id", event.target.value)}>{companies.map((company) => <option key={company.id} value={company.id}>{company.company_name}</option>)}</select></label>
    <label>Email Recipients <span className="optional">(optional)</span><div className="email-recipient-control"><div className="email-chips" aria-live="polite">{form.recipients.map((email) => <span className="email-chip" key={email}>{email}<button type="button" aria-label={`Remove ${email}`} onClick={() => removeRecipient(email)}>×</button></span>)}<input aria-label="Email recipient" value={emailInput} onChange={(event) => { setEmailInput(event.target.value); if (emailError) setEmailError(""); }} onKeyDown={handleEmailKeyDown} onPaste={handleEmailPaste} placeholder="Enter email address and press Enter" /></div>{emailError && <span className="field-error">{emailError}</span>}</div></label>
    <label>Stored Procedure <span className="required">*</span><select required value={form.source_key} onChange={(event) => { update("source_key", event.target.value); setMappings({}); }}>{procedures.map((procedure) => <option key={procedure.key} value={procedure.key}>{procedure.name}{procedure.supports_mapping ? " (mapping enabled)" : ""}</option>)}</select></label>
    {isMappingJob && <div className="mapping-panel"><label>Upload TXT column list <span className="required">*</span><input type="file" accept=".txt,text/plain" onChange={handleUpload} /></label><p className="muted small-note">One report column name per line. UTF-8 TXT only; blank and duplicate names are rejected.</p>{upload && <><p className="mapping-progress">{upload.original_name}: {mappedCount}/{upload.column_names.length} columns mapped</p><div className="mapping-grid"><div><h4>TXT Columns</h4>{upload.column_names.map((name) => <div className="mapping-row" key={name} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(name, event)}><span>{name}</span><select aria-label={`Database field for ${name}`} value={mappings[name] || ""} onChange={(event) => setMapping(name, event.target.value)}><option value="">Select field…</option>{availableFields.filter((field) => !Object.values(mappings).includes(field) || mappings[name] === field).map((field) => <option key={field} value={field}>{field}</option>)}</select></div>)}</div><div><h4>Available Database Fields</h4><div className="field-palette">{unmappedFields.map((field) => <button type="button" draggable onDragStart={() => setDraggedField(field)} key={field} className="field-chip">{field}</button>)}{unmappedFields.length === 0 && <span className="muted">All fields mapped</span>}</div><p className="muted small-note">Drag a field onto a TXT column, or use its dropdown.</p></div></div></>}</div>}
    <div className="form-actions"><button type="submit" disabled={saving}>{saving ? "Scheduling…" : "Create & Schedule Job"}</button>{message && <p className="success">{message}</p>}{error && <p className="error">{error}</p>}</div>
  </form></section></>;
}
