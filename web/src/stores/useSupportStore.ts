import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ============================================================================
   Support cases.

   HONESTY NOTE: DRISHTI has no ticketing backend — there is no support/ticket
   endpoint or table anywhere in the services. Cases raised here are therefore
   recorded in this browser only (localStorage), and the page says so plainly
   rather than showing a "submitted" state that implies a request left the
   machine. When a backend lands, replace the actions below with API calls; the
   shape deliberately mirrors what such an endpoint would accept.
   ========================================================================== */

export type TicketType = "technical" | "data" | "access" | "feature";
export type TicketSeverity = "low" | "normal" | "high" | "urgent";
export type TicketStatus = "open" | "awaiting_response" | "resolved";

export interface TicketMessage {
  id: string;
  /** who wrote it — "you" is the signed-in seat */
  author: string;
  authorKind: "you" | "support";
  body: string;
  at: string;
}

export interface SupportTicket {
  id: string;
  subject: string;
  type: TicketType;
  /** which destination/area the case is about */
  service: string;
  severity: TicketSeverity;
  status: TicketStatus;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  messages: TicketMessage[];
}

export const TICKET_TYPES: { id: TicketType; label: string; blurb: string }[] = [
  { id: "technical", label: "Technical issue", blurb: "Something is broken, erroring or behaving unexpectedly." },
  { id: "data", label: "Data quality", blurb: "A figure, record or boundary looks wrong or stale." },
  { id: "access", label: "Access request", blurb: "A seat, district scope or capability you need." },
  { id: "feature", label: "Feature request", blurb: "Something the platform should be able to do." },
];

export const TICKET_SEVERITIES: { id: TicketSeverity; label: string; blurb: string }[] = [
  { id: "low", label: "Low", blurb: "General guidance; no operational impact." },
  { id: "normal", label: "Normal", blurb: "A function is impaired but work can continue." },
  { id: "high", label: "High", blurb: "Operational work is blocked for a unit." },
  { id: "urgent", label: "Urgent", blurb: "Command-level impact or a live incident is affected." },
];

export const TICKET_STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  awaiting_response: "Awaiting your response",
  resolved: "Resolved",
};

export interface NewTicket {
  subject: string;
  type: TicketType;
  service: string;
  severity: TicketSeverity;
  body: string;
  createdBy: string;
}

interface SupportState {
  tickets: SupportTicket[];
  /** monotonic counter so ids read like real case numbers */
  seq: number;
  create: (input: NewTicket) => string;
  reply: (id: string, body: string, author: string) => void;
  setStatus: (id: string, status: TicketStatus) => void;
}

function nowISO() {
  return new Date().toISOString();
}

function rid() {
  return Math.random().toString(36).slice(2, 10);
}

export const useSupportStore = create<SupportState>()(
  persist(
    (set) => ({
      tickets: [],
      seq: 1041,

      create: (input) => {
        const at = nowISO();
        let id = "";
        set((s) => {
          const seq = s.seq + 1;
          id = `DRI-${seq}`;
          const ticket: SupportTicket = {
            id,
            subject: input.subject.trim(),
            type: input.type,
            service: input.service,
            severity: input.severity,
            status: "open",
            createdAt: at,
            updatedAt: at,
            createdBy: input.createdBy,
            messages: [
              {
                id: rid(),
                author: input.createdBy,
                authorKind: "you",
                body: input.body.trim(),
                at,
              },
            ],
          };
          return { seq, tickets: [ticket, ...s.tickets] };
        });
        return id;
      },

      reply: (id, body, author) =>
        set((s) => ({
          tickets: s.tickets.map((tk) =>
            tk.id !== id
              ? tk
              : {
                  ...tk,
                  status: tk.status === "resolved" ? "open" : tk.status,
                  updatedAt: nowISO(),
                  messages: [
                    ...tk.messages,
                    { id: rid(), author, authorKind: "you" as const, body: body.trim(), at: nowISO() },
                  ],
                },
          ),
        })),

      setStatus: (id, status) =>
        set((s) => ({
          tickets: s.tickets.map((tk) =>
            tk.id === id ? { ...tk, status, updatedAt: nowISO() } : tk,
          ),
        })),
    }),
    {
      name: "drishti.support",
      version: 1,
      partialize: (s) => ({ tickets: s.tickets, seq: s.seq }),
    },
  ),
);

export function severityVariant(s: TicketSeverity): "low" | "medium" | "high" | "critical" {
  if (s === "urgent") return "critical";
  if (s === "high") return "high";
  if (s === "normal") return "medium";
  return "low";
}
