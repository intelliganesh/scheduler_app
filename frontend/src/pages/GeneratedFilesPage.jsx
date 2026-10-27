import { useEffect, useState } from "react";
import DataTable from "../components/DataTable";
import { api } from "../services/api";
import { formatUtcInKolkata } from "../utils/dateTime";

export default function GeneratedFilesPage({ token }) {
  const [files, setFiles] = useState([]); const [error, setError] = useState("");
  useEffect(() => { api.files(token).then(setFiles).catch((err) => setError(err.message)); }, [token]);
  const size = (bytes) => bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
  return <>{error && <div className="inline-error">{error}</div>}<section className="card files-card"><DataTable empty="No generated files yet." columns={[{ key: "file_name", label: "File Name", render: (row) => <span className="file-name">▤ {row.file_name}</span> }, { key: "created_at", label: "Generated At", render: (row) => formatUtcInKolkata(row.created_at) }, { key: "file_size", label: "File Size", render: (row) => size(row.file_size || 0) }, { key: "row_count", label: "Rows" }, { key: "actions", label: "", render: (row) => <button className="small-button" onClick={() => api.downloadFile(token, row.id, row.file_name).catch((err) => setError(err.message))}>Download</button> }]} rows={files} /></section></>;
}
