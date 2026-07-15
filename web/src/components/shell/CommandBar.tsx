import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  FileText,
  Moon,
  PanelLeft,
  Sparkles,
  Sun,
  User,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { visibleDestinations } from "@/config/destinations";
import { useRole } from "@/providers/RoleProvider";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { useAskStore } from "@/stores/useAskStore";

/* ============================================================================
   ⌘K "Ask DRISHTI" — global command palette + omni-search. "Ask" hands the
   question to the Ask DRISHTI destination (doc 01 §8.6), which seeds the
   composer; it also jumps to destinations and opens records by id. The live
   NL→SQL answering connects in Phase 2. Opens on ⌘K / Ctrl-K.
   ========================================================================== */

export function CommandBar() {
  const open = useUIStore((s) => s.commandOpen);
  const setOpen = useUIStore((s) => s.setCommandOpen);
  const toggleTheme = useUIStore((s) => s.toggleTheme);
  const theme = useUIStore((s) => s.theme);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const { role, isAdmin } = useRole();
  const push = usePeekStore((s) => s.push);
  const commandSeed = useUIStore((s) => s.commandSeed);
  const setCommandSeed = useUIStore((s) => s.setCommandSeed);
  const setAskSeed = useAskStore((s) => s.setPendingSeed);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  // Global hotkey
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  // Pre-fill from "Ask DRISHTI about this…" seeds
  useEffect(() => {
    if (open && commandSeed) {
      setQuery(commandSeed);
      setCommandSeed("");
    }
  }, [open, commandSeed, setCommandSeed]);

  const destinations = visibleDestinations(role, isAdmin);
  const trimmed = query.trim();
  const numberMatch = trimmed.match(/(\d{1,10})/);
  const recordId = numberMatch ? Number(numberMatch[1]) : null;

  function run(action: () => void) {
    setOpen(false);
    setQuery("");
    // let the dialog close before navigation/side-effects
    requestAnimationFrame(action);
  }

  function askDrishti() {
    // ⌘K = Ask DRISHTI everywhere: hand the question to the Ask destination.
    const q = trimmed;
    run(() => {
      setAskSeed(q);
      navigate("/ask?tab=chat");
    });
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Ask DRISHTI, or jump to a destination or record…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No matches. Press Enter to ask DRISHTI.</CommandEmpty>

        {trimmed.length > 0 && (
          <>
            <CommandGroup heading="Ask DRISHTI">
              <CommandItem value={`ask ${trimmed}`} onSelect={askDrishti}>
                <Sparkles className="text-primary" />
                <span className="truncate">
                  Ask: <span className="text-content-dim">“{trimmed}”</span>
                </span>
                <CommandShortcut>↵</CommandShortcut>
              </CommandItem>
            </CommandGroup>

            {recordId !== null && (
              <CommandGroup heading="Open record">
                <CommandItem
                  value={`open case ${recordId}`}
                  onSelect={() =>
                    run(() => push({ kind: "case", id: recordId, label: `Case ${recordId}`, sublabel: "Case" }))
                  }
                >
                  <FileText />
                  Open case #{recordId}
                </CommandItem>
                <CommandItem
                  value={`open person entity ${recordId}`}
                  onSelect={() =>
                    run(() =>
                      push({ kind: "person", id: recordId, label: `Entity ${recordId}`, sublabel: "Person" }),
                    )
                  }
                >
                  <User />
                  Open person / entity #{recordId}
                </CommandItem>
              </CommandGroup>
            )}
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading="Go to">
          {destinations.map((d) => {
            const Icon = d.icon;
            return (
              <CommandItem
                key={d.id}
                value={`${d.label} ${d.keywords?.join(" ") ?? ""}`}
                onSelect={() => run(() => navigate(d.path))}
              >
                <Icon />
                <span>{d.label}</span>
                <span className="ml-2 truncate text-12 text-content-dim">{d.description}</span>
                <ArrowRight className="ml-auto opacity-0 data-[selected=true]:opacity-100" />
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Quick actions">
          <CommandItem value="toggle theme ops desk light dark" onSelect={() => run(toggleTheme)}>
            {theme === "ops" ? <Sun /> : <Moon />}
            Switch to {theme === "ops" ? "Desk (light)" : "Ops (dark)"} theme
          </CommandItem>
          <CommandItem value="toggle sidebar collapse" onSelect={() => run(toggleSidebar)}>
            <PanelLeft />
            Toggle sidebar
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
