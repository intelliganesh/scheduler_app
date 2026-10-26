import { useState } from "react";

export default function ReportForm({ onSubmit }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    try { await onSubmit({ title, description: description || null }); setTitle(""); setDescription(""); setError(""); }
    catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  return <form onSubmit={submit} className="card form">
    <h2>Create a report</h2>
    <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Report title" maxLength={255} required />
    <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description" />
    {error && <p className="error">{error}</p>}
    <button disabled={saving}>{saving ? "Saving…" : "Create report"}</button>
  </form>;
}
