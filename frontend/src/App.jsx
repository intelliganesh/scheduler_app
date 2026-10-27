import { useEffect, useState } from "react";
import AppLayout from "./components/AppLayout";
import LoginPanel from "./components/LoginPanel";
import CreateJobForm from "./components/CreateJobForm";
import DashboardPage from "./pages/DashboardPage";
import ScheduledJobsPage from "./pages/ScheduledJobsPage";
import TaskManagementPage from "./pages/TaskManagementPage";
import GeneratedFilesPage from "./pages/GeneratedFilesPage";
import ConfiguredMenuPage from "./pages/ConfiguredMenuPage";
import JobsPage from "./pages/JobsPage";
import DeletionCenterPage from "./pages/DeletionCenterPage";
import { api } from "./services/api";

export default function App() {
  const [user, setUser] = useState(null); const [menus, setMenus] = useState([]); const [menuItems, setMenuItems] = useState([]); const [page, setPage] = useState("dashboard"); const [authError, setAuthError] = useState(""); const [token, setToken] = useState(() => sessionStorage.getItem("access_token"));
  function applyPermissions(permissions) {
    const allowedMenus = permissions.menus || []; const items = permissions.menu_items || [];
    setMenus(allowedMenus); setMenuItems(items);
    const fromUrl = items.find((item) => item.path === window.location.pathname)?.id;
    const nextPage = window.location.pathname === "/jobs/new" && allowedMenus.includes("jobs") ? "jobs_new" : (fromUrl && allowedMenus.includes(fromUrl) ? fromUrl : (allowedMenus.includes("dashboard") ? "dashboard" : allowedMenus[0]));
    setPage(nextPage);
    const nextItem = items.find((item) => item.id === nextPage);
    if (nextPage !== "jobs_new" && nextItem?.path && window.location.pathname !== nextItem.path) window.history.replaceState({}, "", nextItem.path);
  }
  function navigate(nextPage) {
    if (nextPage === "jobs_new") { setPage(nextPage); window.history.pushState({}, "", "/jobs/new"); return; }
    if (!menus.includes(nextPage)) return;
    setPage(nextPage);
    const item = menuItems.find((candidate) => candidate.id === nextPage);
    if (item?.path && window.location.pathname !== item.path) window.history.pushState({}, "", item.path);
  }
  useEffect(() => {
    function onPopState() {
      if (window.location.pathname === "/jobs/new") { setPage("jobs_new"); return; }
      const item = menuItems.find((candidate) => candidate.path === window.location.pathname);
      if (item && menus.includes(item.id)) setPage(item.id);
    }
    window.addEventListener("popstate", onPopState); return () => window.removeEventListener("popstate", onPopState);
  }, [menuItems, menus]);
  useEffect(() => { if (!token) return; Promise.all([api.me(token), api.menus(token)]).then(([profile, permissions]) => { setUser(profile); applyPermissions(permissions); }).catch(() => { sessionStorage.removeItem("access_token"); setToken(null); }); }, [token]);
  async function login(username, password) { const response = await api.login(username, password); sessionStorage.setItem("access_token", response.access_token); setToken(response.access_token); const permissions = await api.menus(response.access_token); setUser(response.user); applyPermissions(permissions); setAuthError(""); }
  function logout() { sessionStorage.removeItem("access_token"); setToken(null); setUser(null); setMenus([]); setMenuItems([]); setAuthError(""); window.history.replaceState({}, "", "/"); }
  if (!user) return <LoginPanel error={authError} onLogin={async (...args) => { try { await login(...args); } catch (err) { setAuthError(err.message); throw err; } }} />;
  const configuredItem = menuItems.find((item) => item.id === page);
  const content = page === "dashboard" ? <DashboardPage token={token} menus={menus} onNavigate={navigate} /> : page === "jobs" ? <JobsPage token={token} onNavigate={navigate} /> : page === "jobs_new" ? <CreateJobForm token={token} onCreated={() => navigate("jobs")} onCancel={() => navigate("jobs")} /> : page === "create_job" ? <CreateJobForm token={token} onCreated={() => navigate("jobs")} onCancel={() => navigate("jobs")} /> : page === "scheduled_jobs" ? <ScheduledJobsPage token={token} onNavigate={navigate} /> : page === "task_management" ? <TaskManagementPage token={token} /> : page === "generated_files" ? <GeneratedFilesPage token={token} /> : page === "deletion_center" ? <DeletionCenterPage token={token} /> : <ConfiguredMenuPage item={configuredItem} />;
  return <AppLayout user={user} menus={menus} menuItems={menuItems} page={page} setPage={navigate} onLogout={logout}>{content}</AppLayout>;
}
