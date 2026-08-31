import { useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Info,
  LifeBuoy,
  Plus,
  Send,
} from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DESTINATIONS } from "@/config/destinations";
import { useRole } from "@/providers/RoleProvider";
import {
  TICKET_SEVERITIES,
  TICKET_STATUS_LABEL,
  TICKET_TYPES,
  severityVariant,
  useSupportStore,
  type SupportTicket,
  type TicketSeverity,
  type TicketType,
} from "@/stores/useSupportStore";

/* ============================================================================
   Support — the AWS Support Center pattern: a case list with severities and
   statuses, a guided "create case" form, and a correspondence thread per case.

   Cases are stored in THIS BROWSER only; DRISHTI has no ticketing service. The
   banner says so, because a support page that looks like it filed a ticket and
   silently did not is worse than one that is honest about it.
   ========================================================================== */

const SERVICE_OPTIONS = [
  { value: "platform", label: "Platform / sign-in" },
  ...DESTINATIONS.map((d) => ({ value: d.id, label: d.label })),
];

function serviceLabel(id: string): string {
  return SERVICE_OPTIONS.find((s) => s.value === id)?.label ?? id;
}

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Support() {
  const { def } = useRole();
  const tickets = useSupportStore((s) => s.tickets);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const selected = tickets.find((t) => t.id === openId) ?? null;
  const openCases = useMemo(() => tickets.filter((t) => t.status !== "resolved"), [tickets]);

  if (selected) {
    return <TicketDetail ticket={selected} onBack={() => setOpenId(null)} actor={def.demoName} />;
  }

  return (
    <div>
      <PageHeader
        title="Support"
        description="Raise a case for a technical issue, a data problem, an access request or a feature idea."
        info={
          <div className="space-y-2">
            <p>
              Cases are grouped by severity so command-impacting problems are visible ahead of
              general questions.
            </p>
            <p>
              This build has no ticketing service behind it, so cases you raise stay in this
              browser. Nothing is transmitted.
            </p>
          </div>
        }
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> Create case
          </Button>
        }
      />

      <LocalOnlyNotice />

      <Tabs defaultValue="open" className="mt-5">
        <TabsList>
          <TabsTrigger value="open">Open cases ({formatNumber(openCases.length)})</TabsTrigger>
          <TabsTrigger value="all">All cases ({formatNumber(tickets.length)})</TabsTrigger>
        </TabsList>
        <TabsContent value="open">
          <TicketTable tickets={openCases} onOpen={setOpenId} emptyLabel="No open cases." />
        </TabsContent>
        <TabsContent value="all">
          <TicketTable
            tickets={tickets}
            onOpen={setOpenId}
            emptyLabel="You have not raised a case yet."
          />
        </TabsContent>
      </Tabs>

      <CreateCaseDialog
        open={creating}
        onOpenChange={setCreating}
        actor={def.demoName}
        onCreated={(id) => {
          setCreating(false);
          setOpenId(id);
        }}
      />
    </div>
  );
}

/* ------------------------------- local notice ----------------------------- */
function LocalOnlyNotice() {
  return (
    <div className="flex items-start gap-2 rounded-card border border-severity-medium/40 bg-severity-medium/5 px-4 py-3">
      <Info className="mt-0.5 size-4 shrink-0 text-severity-medium" />
      <p className="text-body-m text-content-dim">
        <span className="font-bold text-content">Recorded locally.</span> This deployment has no
        ticketing service connected, so cases are kept in your browser and are not sent to a support
        team. The workflow below is the real one — only the transport is missing.
      </p>
    </div>
  );
}

/* --------------------------------- table ---------------------------------- */
function TicketTable({
  tickets,
  onOpen,
  emptyLabel,
}: {
  tickets: SupportTicket[];
  onOpen: (id: string) => void;
  emptyLabel: string;
}) {
  if (!tickets.length) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-card border border-hairline bg-surface py-12 text-center">
        <LifeBuoy className="size-5 text-content-dim" />
        <p className="text-body-m text-content-dim">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-card border border-hairline bg-surface">
      <table className="w-full text-body-m">
        <thead className="border-b border-hairline bg-surface-2/40 text-body-s text-content-dim">
          <tr>
            <th className="px-4 py-2.5 text-left font-bold">Case ID</th>
            <th className="px-4 py-2.5 text-left font-bold">Subject</th>
            <th className="px-4 py-2.5 text-left font-bold">Severity</th>
            <th className="px-4 py-2.5 text-left font-bold">Status</th>
            <th className="px-4 py-2.5 text-left font-bold">Area</th>
            <th className="px-4 py-2.5 text-left font-bold">Last updated</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr
              key={t.id}
              className="cursor-pointer border-b border-hairline last:border-0 transition-colors hover:bg-surface-2/50"
              onClick={() => onOpen(t.id)}
            >
              <td className="px-4 py-3">
                <button
                  type="button"
                  className="tnum font-bold text-primary underline-offset-2 hover:underline"
                >
                  {t.id}
                </button>
              </td>
              <td className="max-w-[22rem] truncate px-4 py-3 text-content">{t.subject}</td>
              <td className="px-4 py-3">
                <Badge variant={severityVariant(t.severity)}>
                  {TICKET_SEVERITIES.find((s) => s.id === t.severity)?.label ?? t.severity}
                </Badge>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={t.status} />
              </td>
              <td className="px-4 py-3 text-content-dim">{serviceLabel(t.service)}</td>
              <td className="tnum px-4 py-3 text-content-dim">{when(t.updatedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: SupportTicket["status"] }) {
  if (status === "resolved") {
    return (
      <Badge variant="low">
        <CheckCircle2 className="size-3" /> {TICKET_STATUS_LABEL.resolved}
      </Badge>
    );
  }
  return (
    <Badge variant={status === "awaiting_response" ? "medium" : "primary"}>
      {TICKET_STATUS_LABEL[status]}
    </Badge>
  );
}

/* ------------------------------ create dialog ----------------------------- */
function CreateCaseDialog({
  open,
  onOpenChange,
  actor,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  actor: string;
  onCreated: (id: string) => void;
}) {
  const create = useSupportStore((s) => s.create);
  const [type, setType] = useState<TicketType>("technical");
  const [service, setService] = useState("platform");
  const [severity, setSeverity] = useState<TicketSeverity>("normal");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  const subjectOk = subject.trim().length >= 5;
  const bodyOk = body.trim().length >= 20;
  const canSubmit = subjectOk && bodyOk;

  const reset = () => {
    setType("technical");
    setService("platform");
    setSeverity("normal");
    setSubject("");
    setBody("");
  };

  const submit = () => {
    if (!canSubmit) return;
    const id = create({ subject, type, service, severity, body, createdBy: actor });
    reset();
    onCreated(id);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-heading-l font-bold">Create case</DialogTitle>
          <DialogDescription>
            Describe the problem as you would to a colleague — what you expected, what happened, and
            where.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Case type" hint={TICKET_TYPES.find((t) => t.id === type)?.blurb}>
            <NativeSelect
              aria-label="Case type"
              value={type}
              onChange={(v) => setType(v as TicketType)}
              options={TICKET_TYPES.map((t) => ({ value: t.id, label: t.label }))}
              placeholder="Technical issue"
            />
          </Field>

          <Field label="Area">
            <NativeSelect
              aria-label="Area"
              value={service}
              onChange={setService}
              options={SERVICE_OPTIONS}
              placeholder="Platform / sign-in"
            />
          </Field>

          <Field
            label="Severity"
            hint={TICKET_SEVERITIES.find((s) => s.id === severity)?.blurb}
            className="sm:col-span-2"
          >
            <div className="flex flex-wrap gap-1.5">
              {TICKET_SEVERITIES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSeverity(s.id)}
                  aria-pressed={severity === s.id}
                  className={cn(
                    "rounded-full border px-3 py-1 text-body-s font-bold transition-colors",
                    severity === s.id
                      ? "border-primary bg-primary/12 text-primary"
                      : "border-hairline text-content-dim hover:bg-surface-2 hover:text-content",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </Field>

          <Field
            label="Subject"
            className="sm:col-span-2"
            error={subject.length > 0 && !subjectOk ? "Give the case a short, specific title." : undefined}
          >
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="District forecast widget fails to load for Udupi"
              maxLength={160}
            />
          </Field>

          <Field
            label="Description"
            className="sm:col-span-2"
            hint={`${body.trim().length} / 20 characters minimum`}
            error={body.length > 0 && !bodyOk ? "Add a little more detail so this is actionable." : undefined}
          >
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              placeholder="What did you expect to see, what did you see instead, and which screen were you on?"
              className={cn(
                "w-full resize-y rounded-control border border-hairline bg-surface-2 px-3 py-2 text-body-m text-content",
                "placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
              )}
            />
          </Field>
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            Create case
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={cn("block space-y-1.5", className)}>
      <span className="block text-body-s font-bold text-content">{label}</span>
      {children}
      {error ? (
        <span className="block text-body-s text-severity-high">{error}</span>
      ) : hint ? (
        <span className="block text-body-s text-content-dim">{hint}</span>
      ) : null}
    </label>
  );
}

/* -------------------------------- detail ---------------------------------- */
function TicketDetail({
  ticket,
  onBack,
  actor,
}: {
  ticket: SupportTicket;
  onBack: () => void;
  actor: string;
}) {
  const reply = useSupportStore((s) => s.reply);
  const setStatus = useSupportStore((s) => s.setStatus);
  const [draft, setDraft] = useState("");

  const send = () => {
    if (draft.trim().length < 2) return;
    reply(ticket.id, draft, actor);
    setDraft("");
  };

  return (
    <div>
      <Button variant="ghost" size="sm" onClick={onBack} className="mb-3 -ml-2">
        <ArrowLeft /> All cases
      </Button>

      <PageHeader
        title={ticket.subject}
        description={`Case ${ticket.id} · raised ${when(ticket.createdAt)} by ${ticket.createdBy}`}
        info={
          <p>
            The correspondence below is stored in this browser. Resolving a case is a local status
            change, not a notification to anyone.
          </p>
        }
        actions={
          ticket.status === "resolved" ? (
            <Button variant="outline" onClick={() => setStatus(ticket.id, "open")}>
              Reopen case
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setStatus(ticket.id, "resolved")}>
              <CheckCircle2 /> Resolve case
            </Button>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge variant={severityVariant(ticket.severity)}>
          {TICKET_SEVERITIES.find((s) => s.id === ticket.severity)?.label} severity
        </Badge>
        <StatusBadge status={ticket.status} />
        <Badge variant="neutral">{TICKET_TYPES.find((t) => t.id === ticket.type)?.label}</Badge>
        <Badge variant="neutral">{serviceLabel(ticket.service)}</Badge>
      </div>

      <div className="space-y-3">
        {ticket.messages.map((m) => (
          <article
            key={m.id}
            className="rounded-card border border-hairline bg-surface p-5 shadow-card"
          >
            <header className="mb-2 flex flex-wrap items-center gap-2 text-body-s text-content-dim">
              <span className="font-bold text-content">{m.author}</span>
              {m.authorKind === "you" && <Badge variant="neutral">You</Badge>}
              <span className="tnum ml-auto">{when(m.at)}</span>
            </header>
            <p className="whitespace-pre-wrap text-body-m text-content">{m.body}</p>
          </article>
        ))}
      </div>

      <div className="mt-4 rounded-card border border-hairline bg-surface p-5 shadow-card">
        <h2 className="mb-2 text-heading-m font-bold text-content">Add a reply</h2>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={4}
          placeholder="Add anything new you have found, or the steps you have already tried."
          className={cn(
            "w-full resize-y rounded-control border border-hairline bg-surface-2 px-3 py-2 text-body-m text-content",
            "placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          )}
        />
        <div className="mt-3 flex justify-end">
          <Button onClick={send} disabled={draft.trim().length < 2}>
            <Send /> Add reply
          </Button>
        </div>
      </div>
    </div>
  );
}
