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
import JobDetailsPage from "./pages/JobDetailsPage";
import { api } from "./services/api";

export default function App() {
    const [user, setUser] = useState(null); const [menus, setMenus] = useState([]); const [menuItems, setMenuItems] = useState([]); const [page, setPage] = useState("dashboard"); const [editingJob, setEditingJob] = useState(null); const [authError, setAuthError] = useState(""); const [token, setToken] = useState(() => sessionStorage.getItem("access_token"));
  function applyPermissions(permissions) {
    const hiddenMenus = new Set(["dashboard", "generated_files"]);
    const allowedMenus = (permissions.menus || []).filter((menu) => !hiddenMenus.has(menu)); const items = (permissions.menu_items || []).filter((item) => !hiddenMenus.has(item.id));
    setMenus(allowedMenus); setMenuItems(items);
    const fromUrl = items.find((item) => item.path === window.location.pathname)?.id;
    const detailPath = /^\/jobs\/(\d+)$/.test(window.location.pathname);
    const nextPage = detailPath && allowedMenus.includes("jobs") ? "jobs_details" : window.location.pathname === "/jobs/new" && allowedMenus.includes("jobs") ? "jobs_new" : (fromUrl && allowedMenus.includes(fromUrl) ? fromUrl : (allowedMenus.includes("jobs") ? "jobs" : allowedMenus[0]));
    setPage(nextPage);
    const nextItem = items.find((item) => item.id === nextPage);
    if (nextPage !== "jobs_new" && nextItem?.path && window.location.pathname !== nextItem.path) window.history.replaceState({}, "", nextItem.path);
  }
  function navigate(nextPage, payload = null) {
    if (nextPage === "jobs_new") { setPage(nextPage); window.history.pushState({}, "", "/jobs/new"); return; }
    if (nextPage === "jobs_edit" && payload) { setEditingJob(payload); setPage(nextPage); window.history.pushState({}, "", `/jobs/${payload.id}/edit`); return; }
    if (nextPage === "jobs_details" && payload) { setEditingJob(payload); setPage(nextPage); window.history.pushState({}, "", `/jobs/${payload.id}`); return; }
    if (!menus.includes(nextPage)) return;
    setPage(nextPage);
    const item = menuItems.find((candidate) => candidate.id === nextPage);
    if (item?.path && window.location.pathname !== item.path) window.history.pushState({}, "", item.path);
  }
  useEffect(() => {
    function onPopState() {
      if (window.location.pathname === "/jobs/new") { setPage("jobs_new"); return; }
      if (/^\/jobs\/\d+$/.test(window.location.pathname)) { setPage("jobs_details"); return; }
      const item = menuItems.find((candidate) => candidate.path === window.location.pathname);
      if (item && menus.includes(item.id)) setPage(item.id);
    }
    window.addEventListener("popstate", onPopState); return () => window.removeEventListener("popstate", onPopState);
  }, [menuItems, menus]);
  useEffect(() => { if (!token) return; Promise.all([api.me(token), api.menus(token)]).then(([profile, permissions]) => { setUser(profile); applyPermissions(permissions); }).catch(() => { sessionStorage.removeItem("access_token"); setToken(null); }); }, [token]);
  useEffect(() => {
    if (!token) return undefined;
    const report = (message, source) => { api.clientError(token, { message: String(message).slice(0, 1000), source }).catch(() => {}); };
    const onError = (event) => report(event.error?.message || event.message || "Unhandled browser error", "window.error");
    const onRejection = (event) => report(event.reason?.message || event.reason || "Unhandled promise rejection", "window.unhandledrejection");
    window.addEventListener("error", onError); window.addEventListener("unhandledrejection", onRejection);
    return () => { window.removeEventListener("error", onError); window.removeEventListener("unhandledrejection", onRejection); };
  }, [token]);
  useEffect(() => {
    if (!token || page !== "jobs_details" || editingJob) return;
    const match = window.location.pathname.match(/^\/jobs\/(\d+)$/);
    if (!match) return;
    api.jobs(token).then((items) => setEditingJob(items.find((item) => String(item.id) === match[1]) || null)).catch(() => setEditingJob(null));
  }, [token, page, editingJob]);
  async function login(username, password) { const response = await api.login(username, password); sessionStorage.setItem("access_token", response.access_token); setToken(response.access_token); const permissions = await api.menus(response.access_token); setUser(response.user); applyPermissions(permissions); setAuthError(""); }
  function logout() { sessionStorage.removeItem("access_token"); setToken(null); setUser(null); setMenus([]); setMenuItems([]); setAuthError(""); window.history.replaceState({}, "", "/"); }
  if (!user) return <LoginPanel error={authError} onLogin={async (...args) => { try { await login(...args); } catch (err) { setAuthError(err.message); throw err; } }} />;
  const configuredItem = menuItems.find((item) => item.id === page);
  const content = page === "dashboard" ? <DashboardPage token={token} menus={menus} onNavigate={navigate} /> : page === "jobs" ? <JobsPage token={token} onNavigate={navigate} onEdit={(job) => navigate("jobs_edit", job)} onViewDetails={(job) => navigate("jobs_details", job)} /> : page === "jobs_new" ? <CreateJobForm token={token} onCreated={() => navigate("jobs")} onCancel={() => navigate("jobs")} /> : page === "jobs_edit" ? <CreateJobForm token={token} editJob={editingJob} onCreated={() => { setEditingJob(null); navigate("jobs"); }} onCancel={() => { setEditingJob(null); navigate("jobs"); }} /> : page === "jobs_details" ? <JobDetailsPage token={token} job={editingJob} onBack={() => { setEditingJob(null); navigate("jobs"); }} /> : page === "create_job" ? <CreateJobForm token={token} onCreated={() => navigate("jobs")} onCancel={() => navigate("jobs")} /> : page === "scheduled_jobs" ? <ScheduledJobsPage token={token} onNavigate={navigate} /> : page === "task_management" ? <TaskManagementPage token={token} /> : page === "generated_files" ? <GeneratedFilesPage token={token} /> : page === "deletion_center" ? <DeletionCenterPage token={token} /> : <ConfiguredMenuPage item={configuredItem} />;
  return <AppLayout user={user} menus={menus} menuItems={menuItems} page={page} setPage={navigate} onLogout={logout}>{content}</AppLayout>;
}
