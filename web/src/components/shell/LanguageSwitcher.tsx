import { Languages } from "lucide-react";
import { cn } from "@/lib/utils";
import { LANGUAGE_OPTIONS, useLanguage, type Language } from "@/providers/LanguageProvider";
import { SimpleTooltip } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/* ============================================================================
   Interface language (EN / ಕನ್ನಡ) in the top bar.

   Kannada is first-class here rather than buried in a settings menu: on a
   Karnataka police deployment the operator's language is a working condition,
   not a preference. Each option is shown in its own script so it is legible to
   the person who needs it.
   ========================================================================== */

/** Short code for the trigger — the native script for Kannada. */
const SHORT: Record<Language, string> = { en: "EN", kn: "ಕನ್ನಡ" };

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, setLanguage, t } = useLanguage();

  return (
    <DropdownMenu>
      <SimpleTooltip label={t("Interface language")}>
        <DropdownMenuTrigger
          className={cn(
            "flex h-8 shrink-0 items-center gap-1.5 rounded-control px-2 text-13 text-content-dim",
            "transition-colors hover:bg-surface-2 hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            className,
          )}
          aria-label={t("Interface language")}
        >
          <Languages className="size-4" />
          <span className={cn("font-bold", language === "kn" && "font-kannada")} lang={language}>
            {SHORT[language]}
          </span>
        </DropdownMenuTrigger>
      </SimpleTooltip>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>{t("Interface language")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={language}
          onValueChange={(v) => setLanguage(v as Language)}
        >
          {LANGUAGE_OPTIONS.map((o) => (
            <DropdownMenuRadioItem key={o.value} value={o.value}>
              <span className="flex min-w-0 flex-col">
                <span
                  className={cn("truncate text-body-m text-content", o.value === "kn" && "font-kannada")}
                  lang={o.value}
                >
                  {o.nativeLabel}
                </span>
                {o.nativeLabel !== o.label && (
                  <span className="truncate text-body-s text-content-dim">{o.label}</span>
                )}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
