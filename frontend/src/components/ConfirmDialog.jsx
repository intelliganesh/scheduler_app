export default function ConfirmDialog({ open, title = "Confirm action", message, confirmLabel = "Confirm", danger = false, onConfirm, onCancel }) {
  if (!open) return null;
  return <div className="modal-backdrop confirm-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel?.(); }}>
    <div className="modal-panel confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
      <div className="modal-header"><h3 id="confirm-dialog-title">{title}</h3><button type="button" className="icon-button" aria-label="Close" onClick={onCancel}>×</button></div>
      <p className="confirm-dialog-message">{message}</p>
      <div className="confirm-dialog-actions"><button type="button" className="small-button secondary" onClick={onCancel}>Cancel</button><button type="button" className={danger ? "small-button danger-button" : "small-button"} onClick={onConfirm}>{confirmLabel}</button></div>
    </div>
  </div>;
}
