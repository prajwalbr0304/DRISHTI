import { apiClient } from "@/api/client";

/* Phase-15 notifications / work tasks (services/ml/app/notifications). Bodies are
   data-minimized synthetic summaries only. Browser -> FastAPI only. */

export interface NotificationDelivery {
  notification_delivery_id: number;
  channel: string;
  provider: string;
  status: string;
  detail: Record<string, unknown>;
  created_at?: string | null;
  delivered_at?: string | null;
}
export interface NotificationItem {
  notification_message_id: number;
  notification_type: string;
  recipient_actor: string;
  summary: string;
  severity: string;
  related_resource?: string | null;
  related_resource_id?: string | null;
  work_task_id?: number | null;
  read_at?: string | null;
  created_at?: string | null;
  deliveries: NotificationDelivery[];
}
export interface NotificationList {
  total: number;
  unread: number;
  items: NotificationItem[];
}
export interface NotificationPreference {
  actor_key: string;
  in_app: boolean;
  email: boolean;
  push: boolean;
  digest_frequency: string;
  escalation_sla_hours: number;
}
export interface WorkTask {
  work_task_id: number;
  task_type: string;
  title: string;
  related_resource?: string | null;
  related_resource_id?: string | null;
  case_master_id?: number | null;
  unit_id?: number | null;
  assignee_actor?: string | null;
  assigned_by_actor?: string | null;
  priority: string;
  status: string;
  due_at?: string | null;
  escalation_sla_hours?: number | null;
  escalated_at?: string | null;
  created_at?: string | null;
}
export interface WorkTaskList {
  total: number;
  items: WorkTask[];
}
export interface EscalationRun {
  checked: number;
  escalated: number;
  notifications_created: number;
  escalated_task_ids: number[];
}

export interface WorkTaskCreateBody {
  task_type?: string;
  title: string;
  related_resource?: string;
  related_resource_id?: string;
  case_master_id?: number;
  unit_id?: number;
  assignee_actor?: string;
  priority?: string;
  due_at?: string;
  escalation_sla_hours?: number;
}

export const notificationsApi = {
  list: (opts: { unread_only?: boolean; limit?: number } = {}, s?: AbortSignal) =>
    apiClient.get<NotificationList>("/notifications", { limit: 50, ...opts }, s),
  markRead: (id: number, s?: AbortSignal) =>
    apiClient.post<NotificationItem>(`/notifications/${id}/read`, undefined, undefined, s),
  getPreferences: (s?: AbortSignal) =>
    apiClient.get<NotificationPreference>("/notifications/preferences", undefined, s),
  updatePreferences: (body: Omit<NotificationPreference, "actor_key">, s?: AbortSignal) =>
    apiClient.request<NotificationPreference>("/notifications/preferences", { method: "PUT", body, signal: s }),
  tasks: (opts: { assignee?: string; status?: string; case_master_id?: number; limit?: number } = {}, s?: AbortSignal) =>
    apiClient.get<WorkTaskList>("/notifications/tasks", { limit: 100, ...opts }, s),
  createTask: (body: WorkTaskCreateBody, s?: AbortSignal) =>
    apiClient.post<WorkTask>("/notifications/tasks", body, undefined, s),
  updateTask: (id: number, body: { status?: string; assignee_actor?: string; priority?: string; due_at?: string }, s?: AbortSignal) =>
    apiClient.request<WorkTask>(`/notifications/tasks/${id}`, { method: "PATCH", body, signal: s }),
  runEscalations: (s?: AbortSignal) =>
    apiClient.post<EscalationRun>("/notifications/escalations/run", undefined, undefined, s),
};
