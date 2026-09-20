import api from "./api";
import type {
  DashboardData,
  Duplicate,
  DuplicateStatus,
  Incident,
  IncidentStatus,
  JobExecution,
  JobRunType,
  PartnersReport,
  SchedulerJob,
} from "./types";

export const dashboardApi = {
  get: () => api.get<DashboardData>("/dashboard").then((r) => r.data),
};

export const partnersApi = {
  report: (days = 30) => api.get<PartnersReport>("/partners/report", { params: { days } }).then((r) => r.data),
};

export const incidentsApi = {
  list: (status: IncidentStatus | "all" = "open", source_id?: number) =>
    api
      .get<Incident[]>("/incidents", { params: { status, ...(source_id ? { source_id } : {}) } })
      .then((r) => r.data),
  update: (id: number, status: "acknowledged" | "resolved", reactivate_source: boolean) =>
    api.patch<Incident>(`/incidents/${id}`, { status, reactivate_source }).then((r) => r.data),
};

export const jobsApi = {
  list: (job_type?: string, limit = 100) =>
    api
      .get<JobExecution[]>("/jobs", { params: { ...(job_type ? { job_type } : {}), limit } })
      .then((r) => r.data),
  scheduler: () => api.get<{ jobs: SchedulerJob[] }>("/jobs/scheduler").then((r) => r.data),
  run: (type: JobRunType) =>
    api.post<{ status: string; job_type: string }>(`/jobs/${type}/run`).then((r) => r.data),
};

export const duplicatesApi = {
  list: (status: DuplicateStatus | "all" = "suspected") =>
    api.get<Duplicate[]>("/duplicates", { params: { status } }).then((r) => r.data),
  update: (id: number, status: "confirmed" | "rejected") =>
    api.patch(`/duplicates/${id}`, { status }).then((r) => r.data),
};
