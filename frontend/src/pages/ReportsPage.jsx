import CreateJobForm from "../components/CreateJobForm";
import LoginPanel from "../components/LoginPanel";
import { api } from "../services/api";
import { useReports } from "../hooks/useReports";
import { useEffect, useState } from "react";

export default function ReportsPage() {
  const { reports, loading, error, refresh } = useReports();
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState("");
  const [menus, setMenus] = useState([]);

  useEffect(() => {
    const token = sessionStorage.getItem("access_token");
    if (token) Promise.all([api.me(token), api.menus(token)]).then(([profile, permissions]) => { setUser(profile); setMenus(permissions.menus); }).catch(() => sessionStorage.removeItem("access_token"));
  }, []);

  async function createReport(payload) { await api.createReport(payload); await refresh(); }
  async function login(username, password) {
    try {
      const response = await api.login(username, password);
      sessionStorage.setItem("access_token", response.access_token);
      const permissions = await api.menus(response.access_token);
      setUser(response.user); setMenus(permissions.menus); setAuthError("");
    } catch (err) { setAuthError(err.message); }
  }
  function logout() { sessionStorage.removeItem("access_token"); setUser(null); setMenus([]); setAuthError(""); }

  return <main>
    <header><h1>Dashboard</h1></header>
    <LoginPanel user={user} error={authError} onLogin={login} onLogout={logout} />
    {user && <nav className="card menu-nav">{["dashboard", "create_job", "scheduled_jobs", "task_management", "generated_files"].filter((menu) => menus.includes(menu)).map((menu) => <span key={menu}>{menu.replaceAll("_", " ")}</span>)}</nav>}
    {user && menus.includes("create_job") && <CreateJobForm token={sessionStorage.getItem("access_token")} onCreated={refresh} />}
    <section className="card"><h2>Reports</h2>{error && <p className="error">{error}</p>}{loading ? <p>Loading…</p> : reports.length ? <ul>{reports.map((report) => <li key={report.id}><strong>{report.title}</strong><span>{report.description || "No description"}</span></li>)}</ul> : !error && <p>No reports yet. Create one above.</p>}</section>
  </main>;
}
