import { useEffect, useRef, useState } from "react";

export default function SearchableSelect({ value, onChange, options, placeholder = "Select…", ariaLabel, disabled = false }) {
  const [open, setOpen] = useState(false); const [query, setQuery] = useState(""); const root = useRef(null);
  const selected = options.find((option) => String(option.value) === String(value));
  useEffect(() => {
    function close(event) { if (!root.current?.contains(event.target)) setOpen(false); }
    document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close);
  }, []);
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));
  function choose(option) { onChange(String(option.value)); setQuery(""); setOpen(false); }
  return <div className="searchable-select" ref={root}>
    <button type="button" className="searchable-select-trigger" aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel} disabled={disabled} onClick={() => setOpen(!open)}><span className={selected ? "" : "placeholder"}>{selected?.label || placeholder}</span><span className="select-chevron">⌄</span></button>
    {open && <div className="searchable-select-menu" role="listbox"><input autoFocus className="searchable-select-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search…" aria-label={`Search ${ariaLabel || "options"}`} />{filtered.length ? filtered.map((option) => <button type="button" role="option" aria-selected={String(option.value) === String(value)} className={`searchable-select-option ${String(option.value) === String(value) ? "selected" : ""}`} key={option.value} onClick={() => choose(option)}>{option.label}</button>) : <span className="searchable-select-empty">No matches</span>}</div>}
  </div>;
}
