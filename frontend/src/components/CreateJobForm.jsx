import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import SearchableSelect from "./SearchableSelect";

const FORMAT_OPTIONS = [
  { value: "Text", label: "Text" },
  { value: "TextPhone", label: "TextPhone" },
  { value: "PhoneDash", label: "Phone (###-###-####)" },
  { value: "PhoneParens", label: "Phone (###) ###-####" },
  { value: "Date", label: "Date (YYYY-MM-DD)" },
  { value: "DateDMY", label: "Date (DD-MM-YYYY)" },
  { value: "DateMDY", label: "Date (MM/DD/YYYY)" },
];

const MAPPED_PROCEDURE = "mapped_employee_payroll_report";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function MultiSelect({ options, values, onAdd, onRemove, placeholder, ariaLabel }) {
  const available = options.filter((option) => !values.includes(String(option.value)));
  return <div className="multi-select-control"><div className="multi-select-chips">{values.map((value) => { const item = options.find((option) => String(option.value) === String(value)); return <span className="email-chip" key={value}>{item?.label || value}<button type="button" aria-label={`Remove ${item?.label || value}`} onClick={() => onRemove(String(value))}>×</button></span>; })}<SearchableSelect value="" onChange={(value) => value && onAdd(String(value))} options={available} placeholder={placeholder} ariaLabel={ariaLabel} /></div></div>;
}

function ManualEmailInput({ clientId, values, draft, error, onDraftChange, onCommit, onRemove }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      onCommit(clientId, draft);
    }
  }
  function handlePaste(event) {
    const pasted = event.clipboardData.getData("text");
    if (pasted.includes(",")) {
      event.preventDefault();
      onCommit(clientId, pasted);
    }
  }
  return <div className="manual-email-control"><div className="email-chips" aria-live="polite">{values.map((email) => <span className="email-chip" key={email}>{email}<button type="button" aria-label={`Remove ${email}`} onClick={() => onRemove(clientId, email)}>×</button></span>)}<input aria-label={`Manual email IDs for company ${clientId}`} value={draft} onChange={(event) => onDraftChange(clientId, event.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste} placeholder="Enter email address and press Enter" /></div>{error && <span className="field-error">{error}</span>}</div>;
}

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

export default function CreateJobForm({ token, onCreated, onCancel, embedded = false }) {
  const [companies, setCompanies] = useState([]); const [procedures, setProcedures] = useState([]);
  const [selectedClientIds, setSelectedClientIds] = useState([]); const [selectedClientEmails, setSelectedClientEmails] = useState({});
  const [emailDrafts, setEmailDrafts] = useState({}); const [emailErrors, setEmailErrors] = useState({});
  const [form, setForm] = useState({ title: "", schedule_at: "", company_id: "", source_key: "", delimiter: ",", export_split_by: "file_name", schedule_type: "one_time", weekly_day: "", monthly_day: "" });
  const [upload, setUpload] = useState(null); const [mappingRows, setMappingRows] = useState([]); const [draggedField, setDraggedField] = useState("");
  const [message, setMessage] = useState(""); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const selectedProcedure = procedures.find((procedure) => procedure.key === form.source_key);
  const availableFields = selectedProcedure?.allowed_fields || []; const isMappingJob = form.source_key === MAPPED_PROCEDURE;
  const mappedCount = mappingRows.filter((row) => row.db_column_name).length;
  const mappedFields = useMemo(() => new Set(mappingRows.map((row) => row.db_column_name).filter(Boolean)), [mappingRows]);
  const [step, setStep] = useState(1);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.companies(token), api.approvedProcedures(token)]).then(([companyList, procedureList]) => {
      setCompanies(companyList); setProcedures(procedureList);
      setForm((current) => ({ ...current, source_key: current.source_key || procedureList.find((item) => item.supports_mapping)?.key || procedureList[0]?.key || "" }));
    }).catch((err) => setError(err.message));
  }, [token]);
  useEffect(() => {
    const valid = new Set(selectedClientIds);
    setSelectedClientEmails((current) => Object.fromEntries(Object.entries(current).filter(([id]) => valid.has(id))));
    setEmailDrafts((current) => Object.fromEntries(Object.entries(current).filter(([id]) => valid.has(id))));
    setEmailErrors((current) => Object.fromEntries(Object.entries(current).filter(([id]) => valid.has(id))));
  }, [token, selectedClientIds]);
  useEffect(() => {
    const dirty = Boolean(form.title || form.schedule_at || selectedClientIds.length || upload || Object.values(selectedClientEmails).some((emails) => emails.length));
    if (!dirty) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [form.title, form.schedule_at, selectedClientIds.length, selectedClientEmails, upload]);
  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); }
  function addClient(id) { setSelectedClientIds((current) => { const next = current.includes(id) ? current : [...current, id]; update("company_id", next[0] || ""); return next; }); }
  function removeClient(id) { setSelectedClientIds((current) => { const next = current.filter((value) => value !== id); update("company_id", next[0] || ""); return next; }); }
  function addClientEmails(clientId, rawValue) {
    const candidates = rawValue.split(",").map((value) => value.trim()).filter(Boolean);
    if (!candidates.length) return;
    const next = [...(selectedClientEmails[clientId] || [])]; const seen = new Set(next.map((email) => email.toLowerCase())); let problem = "";
    for (const email of candidates) {
      if (!EMAIL_PATTERN.test(email)) { problem = `Enter a complete email address, for example name@company.in: ${email}`; continue; }
      if (seen.has(email.toLowerCase())) { problem = `Email address already added: ${email}`; continue; }
      seen.add(email.toLowerCase()); next.push(email);
    }
    setSelectedClientEmails((current) => ({ ...current, [clientId]: next })); setEmailDrafts((current) => ({ ...current, [clientId]: "" })); setEmailErrors((current) => ({ ...current, [clientId]: problem }));
  }
  function removeClientEmail(clientId, email) { setSelectedClientEmails((current) => ({ ...current, [clientId]: (current[clientId] || []).filter((value) => value !== email) })); setEmailErrors((current) => ({ ...current, [clientId]: "" })); }
  function setMapping(name, field) { setMappingRows((current) => current.map((row) => row.column_name === name ? { ...row, db_column_name: field || "" } : row)); }
  function setRecordType(name, record_type) { setMappingRows((current) => current.map((row) => row.column_name === name ? { ...row, record_type } : row)); }
  function setFormat(name, format) { setMappingRows((current) => current.map((row) => row.column_name === name ? { ...row, format } : row)); }
  async function handleUpload(event) {
    const file = event.target.files?.[0]; if (!file) return; setError(""); setMessage("");
    try {
      const result = await api.uploadQuery(token, file);
      const parsed = typeof result.column_names === "string" ? JSON.parse(result.column_names) : result.column_names;
      const rows = (parsed || []).map((item) => typeof item === "string"
        ? { column_name: item, record_type: "D", db_column_name: "", format: "Text" }
        : { column_name: item.column_name || item.display_name, record_type: String(item.record_type || "D").toUpperCase(), db_column_name: item.db_column_name || item.database_field || "", format: item.format || "Text" });
      setUpload({ id: result.id, original_name: result.original_name, column_names: rows.map((row) => row.column_name) });
      setMappingRows(rows); setMessage(`${rows.length} columns loaded. Map each one to an approved field.`);
    }
    catch (err) { event.target.value = ""; setError(err.message); }
  }
  function drop(name, event) { event.preventDefault(); if (draggedField) setMapping(name, draggedField); setDraggedField(""); }
  async function submit(event) {
    event.preventDefault(); setError(""); setMessage("");
    // Keep scheduling strictly behind the review step. This also protects
    // against an accidental Enter/native-control submit while on Step 4.
    if (step !== 5) { nextStep(); return; }
    if (!selectedClientIds.length) { setError("Select at least one company/client before scheduling."); return; }
    if (!form.source_key) { setError("Select a stored procedure before scheduling."); return; }
    if (isMappingJob && (!upload || mappedCount !== mappingRows.length)) { setError("Upload a column list and map every column before scheduling."); return; }
    try { setSaving(true); const schedule_at = scheduleAtInKolkata(form.schedule_at); const clientSelections = Object.fromEntries(selectedClientIds.map((clientId) => [String(clientId), (selectedClientEmails[clientId] || []).map(String)])); await api.createJob(token, { title: form.title, display_name: form.title, schedule_at, company_id: Number(selectedClientIds[0]), source_type: "procedure", source_key: form.source_key, uploaded_query_id: upload?.id || null, column_mappings: isMappingJob ? mappingRows.map((row) => ({ column_name: row.column_name, display_name: row.column_name, record_type: row.record_type, db_column_name: row.db_column_name, database_field: row.db_column_name, format: row.format || "Text" })) : null, delimiter: form.delimiter, export_split_by: form.export_split_by, schedule_type: form.schedule_type, weekly_day: form.weekly_day === "" ? null : Number(form.weekly_day), monthly_day: form.monthly_day === "" ? null : Number(form.monthly_day), client_selections: clientSelections, recipients: [], enabled: true }); setMessage("Job created and scheduled."); setForm((current) => ({ ...current, title: "", schedule_at: "", company_id: "", delimiter: ",", export_split_by: "file_name", schedule_type: "one_time", weekly_day: "", monthly_day: "" })); setSelectedClientIds([]); setSelectedClientEmails({}); setEmailDrafts({}); setEmailErrors({}); setUpload(null); setMappingRows([]); onCreated?.(); }
    catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  const validateStep = (target) => { setError(""); if (target > 1 && (!form.title.trim() || !form.source_key || !form.schedule_at)) return "Complete job name, stored procedure, and execution date/time."; if (target > 1 && form.schedule_type === "weekly" && form.weekly_day === "") return "Choose a weekday."; if (target > 1 && form.schedule_type === "monthly" && form.monthly_day === "") return "Choose a day of the month."; if (target > 2 && !selectedClientIds.length) return "Select at least one company/client."; if (target > 3 && isMappingJob && (!upload || mappedCount !== mappingRows.length)) return "Upload and map every column before continuing."; return ""; };
  function nextStep() { const problem = validateStep(step + 1); if (problem) { setError(problem); return; } setStep((value) => Math.min(5, value + 1)); }
  function handleNext(event) { event.preventDefault(); event.stopPropagation(); nextStep(); }
  function cancelWizard() { if (window.confirm("Discard this unsaved job?")) onCancel?.(); }
  const companyLabel = (id) => companies.find((company) => String(company.id) === String(id))?.company_name || id;
  const scheduleLabel = { one_time: "One Time", hourly_1: "Every 1 Hour", hourly_2: "Every 2 Hours", hourly_4: "Every 4 Hours", daily: "Daily", weekly: "Weekly", monthly: "Monthly" }[form.schedule_type];
  return <section className="wizard-page"><div className="wizard-header"><div><p className="eyebrow">Scheduling</p><h2>New Job</h2><p className="muted">Create, configure, review, and schedule a report job.</p></div><button type="button" className="small-button secondary" onClick={cancelWizard}>Cancel</button></div><div className="wizard-steps">{["Job Details", "Clients & Emails", "Column Mapping", "Export Settings", "Review & Create"].map((label, index) => <button type="button" key={label} className={step === index + 1 ? "wizard-step active" : step > index + 1 ? "wizard-step complete" : "wizard-step"} onClick={() => step > index + 1 && setStep(index + 1)} disabled={step <= index + 1}>{index + 1}<span>{label}</span></button>)}</div><section className="card wizard-card"><form onSubmit={(event) => { event.preventDefault(); if (step === 5) submit(event); else nextStep(); }}>
    {step === 1 && <div className="wizard-section"><h3>Job Details &amp; Scheduling</h3><label>Job Name <span className="required">*</span><input required value={form.title} onChange={(event) => update("title", event.target.value)} placeholder="e.g. Monthly payroll summary" /></label><label>Stored Procedure <span className="required">*</span><SearchableSelect value={form.source_key} onChange={(value) => { update("source_key", value); setMappingRows([]); setUpload(null); }} options={procedures.map((procedure) => ({ value: procedure.key, label: `${procedure.name}${procedure.supports_mapping ? " (mapping enabled)" : ""}` }))} placeholder="Select stored procedure" ariaLabel="Stored Procedure" /></label><label>Schedule Type <span className="required">*</span><SearchableSelect value={form.schedule_type} onChange={(value) => update("schedule_type", value)} options={[{ value: "one_time", label: "One Time" }, { value: "hourly_1", label: "Every 1 Hour" }, { value: "hourly_2", label: "Every 2 Hours" }, { value: "hourly_4", label: "Every 4 Hours" }, { value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }]} placeholder="Select schedule type" ariaLabel="Schedule Type" /></label><label>{form.schedule_type === "one_time" ? "Execution Date & Time" : "Start Date & Time"} <span className="required">*</span><input required type="datetime-local" value={form.schedule_at} onInput={(event) => update("schedule_at", event.target.value)} onChange={(event) => update("schedule_at", event.target.value)} /></label>{form.schedule_type === "weekly" && <label>Day of Week <span className="required">*</span><SearchableSelect value={form.weekly_day} onChange={(value) => update("weekly_day", value)} options={["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"].map((label, value) => ({ value, label }))} placeholder="Select day" ariaLabel="Day of Week" /></label>}{form.schedule_type === "monthly" && <label>Day of Month <span className="required">*</span><SearchableSelect value={form.monthly_day} onChange={(value) => update("monthly_day", value)} options={Array.from({ length: 31 }, (_, index) => ({ value: index + 1, label: String(index + 1) }))} placeholder="Select day" ariaLabel="Day of Month" /></label>}</div>}
    {step === 2 && <div className="wizard-section"><h3>Clients &amp; Email Recipients</h3><p className="step-helper">Select one or more companies, then add optional email recipients for each selected company.</p><div className="client-step-content"><label>Company / Client <span className="required">*</span><MultiSelect options={companies.map((company) => ({ value: company.id, label: `${company.company_name} (Client ID: ${company.id})` }))} values={selectedClientIds} onAdd={addClient} onRemove={removeClient} placeholder="Search companies / clients" ariaLabel="Select Companies / Clients" /></label>{selectedClientIds.length ? <div className="client-email-list" aria-label="Manual email recipients by company">{selectedClientIds.map((clientId) => { const client = companies.find((item) => String(item.id) === String(clientId)); return <div className="client-email-row" key={clientId}><div className="client-email-company"><strong>{client?.company_name || "Client"}</strong><span>Client ID: {clientId}</span></div><ManualEmailInput clientId={String(clientId)} values={selectedClientEmails[clientId] || []} draft={emailDrafts[clientId] || ""} error={emailErrors[clientId] || ""} onDraftChange={(id, value) => { setEmailDrafts((current) => ({ ...current, [id]: value })); if (emailErrors[id]) setEmailErrors((current) => ({ ...current, [id]: "" })); }} onCommit={addClientEmails} onRemove={removeClientEmail} /></div>; })}</div> : <div className="client-empty-state"><strong>No companies selected yet</strong><span>Select a company above to configure its email recipients.</span></div>}</div></div>}
    {step === 3 && <div className="wizard-section mapping-wizard-section"><h3>Excel Upload &amp; Column Mapping</h3>{isMappingJob ? <div className="mapping-panel"><label>Upload column list <span className="required">*</span><input type="file" accept=".txt,.xlsx,.xlsm,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleUpload} /></label><p className="muted small-note">Upload TXT or Excel with record type and column name columns.</p>{upload && <><p className="mapping-progress">{upload.original_name}: {mappedCount}/{mappingRows.length} columns mapped</p><div className="mapping-table-wrap"><table className="mapping-table"><thead><tr><th>Column Name</th><th>Record Type</th><th>DB Column Name</th><th>Format</th></tr></thead><tbody>{mappingRows.map((row) => <tr key={row.column_name} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(row.column_name, event)}><td className="mapping-cell mapping-readonly">{row.column_name}</td><td className="mapping-cell"><select className={`record-type-select record-type-${row.record_type}`} value={row.record_type} onChange={(event) => setRecordType(row.column_name, event.target.value)}><option value="H">H</option><option value="D">D</option><option value="T">T</option></select></td><td className="mapping-cell"><SearchableSelect value={row.db_column_name} onChange={(value) => setMapping(row.column_name, value)} options={availableFields.filter((field) => !mappedFields.has(field) || row.db_column_name === field).map((field) => ({ value: field, label: field }))} placeholder="Select field" ariaLabel={`Database field for ${row.column_name}`} /></td><td className="mapping-cell"><SearchableSelect value={row.format || "Text"} onChange={(value) => setFormat(row.column_name, value)} options={FORMAT_OPTIONS} placeholder="Select format" ariaLabel={`Format for ${row.column_name}`} /></td></tr>)}</tbody></table></div></>}</div> : <p className="muted">This procedure does not require a column list.</p>}</div>}
    {step === 4 && <div className="wizard-section"><h3>Export Settings</h3><label>Select Delimiter <SearchableSelect value={form.delimiter || ","} onChange={(value) => update("delimiter", value)} options={[{ value: ",", label: "Comma (,)" }, { value: "|", label: "Pipe (|)" }, { value: ";", label: "Semicolon (;)" }, { value: "\t", label: "Tab (\\t)" }]} placeholder="Select delimiter" ariaLabel="Select Delimiter" /></label><label>Export Split By <SearchableSelect value={form.export_split_by || "file_name"} onChange={(value) => update("export_split_by", value)} options={[{ value: "file_name", label: "File Name (single CSV)" }, { value: "client_id", label: "Client ID" }, { value: "pay_date", label: "Pay Date (payroll month)" }]} placeholder="Select export split" ariaLabel="Export Split By" /></label><div className="export-help"><p><strong>File Name:</strong> one CSV file containing all records.</p><p><strong>Client ID:</strong> one file per selected company/client.</p><p><strong>Pay Date:</strong> groups records by payroll month.</p></div></div>}
    {step === 5 && <div className="wizard-section"><h3>Review &amp; Create Job</h3><dl className="wizard-review"><dt>Job Name</dt><dd>{form.title || "—"}</dd><dt>Stored Procedure</dt><dd>{form.source_key || "—"}</dd><dt>Schedule</dt><dd>{scheduleLabel} · {form.schedule_at || "—"}</dd><dt>Clients</dt><dd>{selectedClientIds.map(companyLabel).join(", ") || "—"}</dd><dt>Client Email IDs</dt><dd>{selectedClientIds.map((id) => `${companyLabel(id)}: ${(selectedClientEmails[id] || []).join(", ") || "None"}`).join(" · ") || "—"}</dd><dt>Upload</dt><dd>{upload ? `${upload.original_name} (${mappedCount}/${mappingRows.length} mapped)` : "None"}</dd><dt>Delimiter</dt><dd>{form.delimiter === "\t" ? "Tab" : form.delimiter || "Comma (,)"}</dd><dt>Export Split By</dt><dd>{form.export_split_by}</dd></dl></div>}
    {error && <p className="error wizard-error">{error}</p>}<div className="wizard-actions"><button type="button" className="small-button secondary" onClick={() => step === 1 ? cancelWizard() : setStep((value) => value - 1)}>{step === 1 ? "Cancel" : "Back"}</button>{step < 5 ? <button type="button" onClick={handleNext}>Next</button> : <button type="submit" disabled={saving}>{saving ? "Scheduling…" : "Create & Schedule Job"}</button>}</div>
  </form></section></section>;
}
