import { useEffect, useState } from "react";
import AppLayout from "./components/AppLayout";
import LoginPanel from "./components/LoginPanel";
import CreateJobForm from "./components/CreateJobForm";
import DashboardPage from "./pages/DashboardPage";
import ScheduledJobsPage from "./pages/ScheduledJobsPage";
import TaskManagementPage from "./pages/TaskManagementPage";
import GeneratedFilesPage from "./pages/GeneratedFilesPage";
import { api } from "./services/api";

export default function App() {
  const [user, setUser] = useState(null); const [menus, setMenus] = useState([]); const [menuItems, setMenuItems] = useState([]); const [page, setPage] = useState("dashboard"); const [authError, setAuthError] = useState(""); const [token, setToken] = useState(() => sessionStorage.getItem("access_token"));
  function applyPermissions(permissions) { setMenus(permissions.menus || []); setMenuItems(permissions.menu_items || []); setPage((current) => (permissions.menus || []).includes(current) ? current : ((permissions.menus || []).includes("dashboard") ? "dashboard" : permissions.menus?.[0])); }
  function navigate(nextPage) { if (menus.includes(nextPage)) setPage(nextPage); }
  useEffect(() => { if (!token) return; Promise.all([api.me(token), api.menus(token)]).then(([profile, permissions]) => { setUser(profile); applyPermissions(permissions); }).catch(() => { sessionStorage.removeItem("access_token"); setToken(null); }); }, [token]);
  async function login(username, password) { const response = await api.login(username, password); sessionStorage.setItem("access_token", response.access_token); setToken(response.access_token); const permissions = await api.menus(response.access_token); setUser(response.user); applyPermissions(permissions); setAuthError(""); }
  function logout() { sessionStorage.removeItem("access_token"); setToken(null); setUser(null); setMenus([]); setMenuItems([]); setAuthError(""); }
  if (!user) return <LoginPanel error={authError} onLogin={async (...args) => { try { await login(...args); } catch (err) { setAuthError(err.message); throw err; } }} />;
  const content = page === "dashboard" ? <DashboardPage token={token} menus={menus} onNavigate={navigate} /> : page === "create_job" ? <CreateJobForm token={token} onCreated={() => {}} /> : page === "scheduled_jobs" ? <ScheduledJobsPage token={token} onNavigate={navigate} /> : page === "task_management" ? <TaskManagementPage token={token} /> : <GeneratedFilesPage token={token} />;
  return <AppLayout user={user} menus={menus} menuItems={menuItems} page={page} setPage={navigate} onLogout={logout}>{content}</AppLayout>;
}
