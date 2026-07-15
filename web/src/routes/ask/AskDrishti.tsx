import { useSearchParams } from "react-router-dom";
import { Bookmark, History as HistoryIcon, MessageSquareText } from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/common/PageHeader";
import { ChatView } from "@/routes/ask/ChatView";
import { HistoryView } from "@/routes/ask/HistoryView";
import { SavedQueriesView } from "@/routes/ask/SavedQueriesView";

/* ============================================================================
   Ask DRISHTI (doc 01 §4.7) — the conversational workspace. Sub-nav switches
   Chat / History / Saved Queries. The composer, voice, language toggle and the
   grounded answer anatomy (reply · inline citations · read-only SQL · confidence)
   live in Chat; History replays real past sessions; Saved Queries are reusable
   prompts. The live NL→SQL engine connects in Phase 2.
   ========================================================================== */

type Tab = "chat" | "history" | "saved";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "chat", label: "Chat", icon: MessageSquareText },
  { key: "history", label: "History", icon: HistoryIcon },
  { key: "saved", label: "Saved Queries", icon: Bookmark },
];

export function AskDrishti() {
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) ?? "chat";
  const active: Tab = TABS.some((t) => t.key === tab) ? tab : "chat";

  const setTab = (t: Tab) => {
    const next = new URLSearchParams(sp);
    next.set("tab", t);
    setSp(next, { replace: true });
  };

  return (
    <div>
      <PageHeader
        title="Ask DRISHTI"
        description="Conversational, cited answers grounded in the data — in English or Kannada."
      />

      {/* Sub-nav */}
      <div className="mb-4 flex flex-wrap gap-1 border-b border-hairline">
        {TABS.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-2 border-b-2 px-3 py-2 text-13 font-medium transition-colors",
                isActive
                  ? "border-primary text-content"
                  : "border-transparent text-content-dim hover:text-content",
              )}
            >
              <Icon className="size-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {active === "chat" && <ChatView />}
      {active === "history" && <HistoryView onOpened={() => setTab("chat")} />}
      {active === "saved" && <SavedQueriesView onUse={() => setTab("chat")} />}
    </div>
  );
}
