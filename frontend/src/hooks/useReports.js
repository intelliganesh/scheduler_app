import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";

export function useReports() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setReports(await api.getReports()); setError(""); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  return { reports, loading, error, refresh };
}
