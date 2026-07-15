import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Bookmark, Plus, Trash2 } from "lucide-react";
import { api } from "@/api";
import { useAskStore, type AskLang } from "@/stores/useAskStore";
import { useSavedQueriesStore } from "@/stores/useSavedQueriesStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";

/* Saved Queries (doc 01 §4.7): reusable prompts. Persisted client-side until
   the Phase-2 engine adds server persistence. Seeded questions are offered as
   ready-to-save starting points (real prompts, not fabricated answers). */
export function SavedQueriesView({ onUse }: { onUse: () => void }) {
  const queries = useSavedQueriesStore((s) => s.queries);
  const save = useSavedQueriesStore((s) => s.save);
  const remove = useSavedQueriesStore((s) => s.remove);
  const has = useSavedQueriesStore((s) => s.has);
  const setPendingSeed = useAskStore((s) => s.setPendingSeed);
  const setLanguage = useAskStore((s) => s.setLanguage);

  const sessions = useQuery({
    queryKey: ["chat", "sessions"],
    queryFn: ({ signal }) => api.chat.sessions(50, signal),
  });
  const examples = (sessions.data?.sessions ?? [])
    .filter((s) => s.first_question)
    .map((s) => ({ text: s.first_question as string, language: (s.language as AskLang) ?? "en" }));

  const use = (text: string, language: AskLang | string) => {
    setLanguage(language === "kn" ? "kn" : "en");
    setPendingSeed(text);
    onUse();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Saved */}
      <section>
        <h2 className="mb-2 flex items-center gap-2 text-14 font-semibold text-content">
          <Bookmark className="size-4" /> Your saved prompts
        </h2>
        {queries.length === 0 ? (
          <EmptyState
            icon={Bookmark}
            title="No saved prompts yet"
            description="Save a question from the composer (the bookmark icon) to reuse it later. Or add one from the examples below."
          />
        ) : (
          <ul className="space-y-2">
            {queries.map((qq) => (
              <li
                key={qq.id}
                className="flex items-center gap-3 rounded-card border border-hairline bg-surface p-3 shadow-card"
              >
                <span className="min-w-0 flex-1 truncate text-13 text-content" lang={qq.language}>
                  {qq.text}
                </span>
                {qq.language === "kn" && <Badge variant="neutral">ಕನ್ನಡ</Badge>}
                <Button variant="ghost" size="sm" onClick={() => use(qq.text, qq.language)}>
                  Use <ArrowUpRight />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => remove(qq.id)}
                  aria-label="Remove saved prompt"
                  className="text-content-dim hover:text-severity-critical"
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Examples to save/use */}
      {examples.length > 0 && (
        <section>
          <h2 className="mb-2 text-14 font-semibold text-content">Example prompts</h2>
          <ul className="space-y-2">
            {examples.map((ex, i) => {
              const saved = has(ex.text);
              return (
                <li
                  key={`${ex.text}-${i}`}
                  className="flex items-center gap-3 rounded-card border border-hairline bg-surface-2/40 p-3"
                >
                  <span className="min-w-0 flex-1 truncate text-13 text-content" lang={ex.language}>
                    {ex.text}
                  </span>
                  {ex.language === "kn" && <Badge variant="neutral">ಕನ್ನಡ</Badge>}
                  <Button variant="ghost" size="sm" onClick={() => use(ex.text, ex.language)}>
                    Use <ArrowUpRight />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => save(ex.text, ex.language)}
                    disabled={saved}
                    aria-label="Save prompt"
                    title={saved ? "Already saved" : "Save prompt"}
                  >
                    <Plus />
                  </Button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
