import { Moon, Sun } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { Button } from "@/components/ui/button";
import { SimpleTooltip } from "@/components/ui/tooltip";

/* Ops (dark) <-> Desk (light) theme toggle. */
export function ThemeToggle() {
  const theme = useUIStore((s) => s.theme);
  const toggle = useUIStore((s) => s.toggleTheme);
  const isOps = theme === "ops";
  return (
    <SimpleTooltip label={isOps ? "Switch to Desk (light)" : "Switch to Ops (dark)"}>
      <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
        {isOps ? <Moon /> : <Sun />}
      </Button>
    </SimpleTooltip>
  );
}
