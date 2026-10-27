import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export default function SearchableSelect({ value, onChange, options, placeholder = "Select…", ariaLabel, disabled = false }) {
  const [open, setOpen] = useState(false); const [query, setQuery] = useState(""); const [menuStyle, setMenuStyle] = useState({}); const root = useRef(null); const menu = useRef(null);
  const selected = options.find((option) => String(option.value) === String(value));
  useEffect(() => {
    function close(event) { if (!root.current?.contains(event.target) && !menu.current?.contains(event.target)) setOpen(false); }
    document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close);
  }, []);
  useLayoutEffect(() => {
    if (!open) return undefined;
    const positionMenu = () => {
      const rect = root.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(Math.max(rect.width, 220), window.innerWidth - 16);
      const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
      const openUp = window.innerHeight - rect.bottom < 190 && rect.top > 190;
      setMenuStyle({ left, width, right: "auto", ...(openUp ? { top: "auto", bottom: window.innerHeight - rect.top + 5 } : { top: rect.bottom + 5, bottom: "auto" }) });
    };
    positionMenu(); window.addEventListener("resize", positionMenu); window.addEventListener("scroll", positionMenu, true);
    return () => { window.removeEventListener("resize", positionMenu); window.removeEventListener("scroll", positionMenu, true); };
  }, [open]);
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));
  function choose(option) { if (option.disabled) return; onChange(String(option.value)); setQuery(""); setOpen(false); }
  return <div className="searchable-select" ref={root}>
    <button type="button" className="searchable-select-trigger" aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel} disabled={disabled} onClick={() => setOpen(!open)}><span className={selected ? "" : "placeholder"}>{selected?.label || placeholder}</span><span className="select-chevron">⌄</span></button>
    {open && createPortal(<div className="searchable-select-menu" ref={menu} style={{ position: "fixed", zIndex: 1000, ...menuStyle }} role="listbox"><input autoFocus className="searchable-select-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search…" aria-label={`Search ${ariaLabel || "options"}`} />{filtered.length ? filtered.map((option) => <button type="button" role="option" aria-disabled={option.disabled || undefined} aria-selected={String(option.value) === String(value)} className={`searchable-select-option ${String(option.value) === String(value) ? "selected" : ""} ${option.disabled ? "disabled" : ""}`} key={option.value} onClick={() => choose(option)}>{option.label}</button>) : <span className="searchable-select-empty">No matches</span>}</div>, document.body)}
  </div>;
}
