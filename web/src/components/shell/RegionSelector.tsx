import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDistrictLabel, useScopedDistricts } from "@/hooks/useDistricts";
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
  const { districts, allowAll, pinnedTo, unposted, note, allLabel } = useScopedDistricts();
  const label = useDistrictLabel();
  const { t } = useLanguage();

  /* A seat posted to ONE district has nothing to choose. The menu still opens,
     because hiding the control entirely would leave an officer with no way to see
     which jurisdiction the workspace is scoped to — but it states the posting
     rather than offering 37 districts that every endpoint answers 403 for. */
  const single = pinnedTo != null;

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
        <DropdownMenuLabel>
          {single
            ? t("Your posted district")
            : t("Scope this workspace to a district")}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <div className="max-h-[60vh] overflow-y-auto">
          <DropdownMenuRadioGroup
            value={districtId == null ? "" : String(districtId)}
            onValueChange={(v) => setDistrictId(v === "" ? null : Number(v))}
          >
            {/* Offered only when it is TRUE. For a range seat it means "all seven
                districts in my range", which is what the server serves; for a seat
                posted to one district it would be a label describing somewhere
                other than the data underneath it. */}
            {allowAll && (
              <>
                <DropdownMenuRadioItem value="">{t(allLabel)}</DropdownMenuRadioItem>
                <DropdownMenuSeparator />
              </>
            )}
            {districts.map((d) => (
              <DropdownMenuRadioItem key={d.id} value={String(d.id)}>
                <span className="truncate">{d.name}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          {unposted && (
            <p className="px-2 py-3 text-body-s text-content-dim">
              {t("No district is in scope for this seat.")}
            </p>
          )}
        </div>

        <DropdownMenuSeparator />
        {/* The note comes from the seat, so it says which bound is in force rather
            than repeating one generic caveat to every role. */}
        <p className="px-2 py-1.5 text-body-s text-content-dim">{t(note)}</p>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
