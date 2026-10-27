import { API_BASE_URL } from "../config/api";

function errorMessage(detail) {
  // Validation errors (422) arrive as a list of { loc, msg } objects.
  if (Array.isArray(detail)) return detail.map((error) => `${error.loc?.at(-1) ?? "request"}: ${error.msg}`).join("; ");
  return typeof detail === "string" ? detail : "The request failed.";
}

async function request(path, options = {}) {
  let response;
  try {
    const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: isForm ? { ...options.headers } : { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error("Cannot reach the server. Check that the backend is running.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(errorMessage(body.detail));
  }
  return response.json();
}

export const api = {
  health: () => request("/health"),
  clientError: (token, payload) => request("/api/client-errors", { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: JSON.stringify(payload) }),
  getReports: () => request("/api/reports"),
  createReport: (report) => request("/api/reports", { method: "POST", body: JSON.stringify(report) }),
  login: (username, password) => request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: (token) => request("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }),
  menus: (token) => request("/api/auth/menus", { headers: { Authorization: `Bearer ${token}` } }),
  companies: (token) => request("/api/companies", { headers: { Authorization: `Bearer ${token}` } }),
  clients: (token, companyId) => request(`/api/companies/${companyId}/clients`, { headers: { Authorization: `Bearer ${token}` } }),
  clientEmails: (token, clientId) => request(`/api/clients/${clientId}/emails`, { headers: { Authorization: `Bearer ${token}` } }),
  companyEmails: (token, companyId) => request(`/api/companies/${companyId}/emails`, { headers: { Authorization: `Bearer ${token}` } }),
  approvedProcedures: (token) => request("/api/approved-procedures", { headers: { Authorization: `Bearer ${token}` } }),
  uploadQuery: (token, file) => { const body = new FormData(); body.append("file", file); return request("/api/uploads/query", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body }); },
  createJob: (token, job) => request("/api/jobs", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify(job) }),
  updateJob: (token, id, job) => request(`/api/jobs/${id}`, { method: "PUT", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify(job) }),
  jobs: (token) => request("/api/jobs", { headers: { Authorization: `Bearer ${token}` } }),
  dashboard: (token) => request("/api/dashboard", { headers: { Authorization: `Bearer ${token}` } }),
  runs: (token) => request("/api/runs", { headers: { Authorization: `Bearer ${token}` } }),
  files: (token) => request("/api/files", { headers: { Authorization: `Bearer ${token}` } }),
  deletionSummary: (token) => request("/api/deletion-center", { headers: { Authorization: `Bearer ${token}` } }),
  deleteAllJobsAndFiles: (token) => request("/api/deletion-center", { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }),
  runJob: (token, id) => request(`/api/jobs/${id}/run`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }),
  toggleJob: (token, id, enabled) => request(`/api/jobs/${id}/enabled?enabled=${enabled}`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }),
  retryRun: (token, id) => request(`/api/runs/${id}/retry`, { method: "POST", headers: { Authorization: `Bearer ${token}` } }),
  downloadFile: async (token, id, name) => {
    const response = await fetch(`${API_BASE_URL}/api/files/${id}/download`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error("The file could not be downloaded.");
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = name || "report.csv"; link.click(); URL.revokeObjectURL(url);
  },
};
