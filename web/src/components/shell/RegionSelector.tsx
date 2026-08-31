import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDistrictLabel, useDistricts } from "@/hooks/useDistricts";
import { useScopeStore } from "@/stores/useScopeStore";
import { useLanguage } from "@/providers/LanguageProvider";
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
   District selector — the DRISHTI equivalent of the AWS console region menu:
   a plain text trigger on the right of the top bar that re-scopes the whole
   workspace.

   Presented as a view filter, never as permission. The server enforces what a
   role may read from the X-Role header, so picking a district can only narrow
   what is shown, never widen it.
   ========================================================================== */

export function RegionSelector({ className }: { className?: string }) {
  const districtId = useScopeStore((s) => s.districtId);
  const setDistrictId = useScopeStore((s) => s.setDistrictId);
  const { districts, usingFallback } = useDistricts();
  const label = useDistrictLabel();
  const { t } = useLanguage();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-8 shrink-0 items-center gap-1.5 rounded-control px-2.5 text-13 text-content",
          "transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          className,
        )}
        aria-label={t("District scope")}
      >
        <span className="max-w-[13rem] truncate">{t(label)}</span>
        <ChevronDown className="size-3.5 shrink-0 text-content-dim" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>{t("Scope this workspace to a district")}</DropdownMenuLabel>
        <DropdownMenuSeparator />

        <div className="max-h-[60vh] overflow-y-auto">
          <DropdownMenuRadioGroup
            value={districtId == null ? "" : String(districtId)}
            onValueChange={(v) => setDistrictId(v === "" ? null : Number(v))}
          >
            <DropdownMenuRadioItem value="">{t("All districts")}</DropdownMenuRadioItem>
            <DropdownMenuSeparator />
            {districts.map((d) => (
              <DropdownMenuRadioItem key={d.id} value={String(d.id)}>
                <span className="truncate">{d.name}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </div>

        <DropdownMenuSeparator />
        <p className="px-2 py-1.5 text-body-s text-content-dim">
          {usingFallback
            ? t("Showing the districts available to this seat. A view filter only — it cannot widen what your role may read.")
            : t("A view filter only — it cannot widen what your role may read.")}
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
