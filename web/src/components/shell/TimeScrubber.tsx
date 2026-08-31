import { useEffect } from "react";
import { CalendarClock, ChevronDown, Pause, Play, RotateCcw } from "lucide-react";
import { cn, formatDate, formatDateTime } from "@/lib/utils";
import { PRESETS, playheadDate, useTimeStore } from "@/stores/useTimeStore";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { useLanguage } from "@/providers/LanguageProvider";

/* ============================================================================
   Global time-scrubber. One window scopes every time-aware widget; the playhead
   animates through it. Presets snap the window; play advances the playhead.
   ========================================================================== */

const PLAY_STEP = 0.02; // per tick
const PLAY_INTERVAL = 220; // ms

export function TimeScrubber() {
  const { preset, start, end, playhead, playing } = useTimeStore();
  const setPreset = useTimeStore((s) => s.setPreset);
  const setPlayhead = useTimeStore((s) => s.setPlayhead);
  const togglePlay = useTimeStore((s) => s.togglePlay);
  const setPlaying = useTimeStore((s) => s.setPlaying);
  const { t } = useLanguage();

  // Play loop — advance the playhead, wrap around at the end.
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      const next = playhead + PLAY_STEP;
      setPlayhead(next >= 1 ? 0 : next);
    }, PLAY_INTERVAL);
    return () => clearInterval(t);
  }, [playing, playhead, setPlayhead]);

  const label =
    preset === "custom"
      ? `${formatDate(start)} – ${formatDate(end)}`
      : t(PRESETS.find((p) => p.id === preset)?.label ?? "Custom");

  const headDate = playheadDate(start, end, playhead);
  const scrubbing = playhead < 0.999;

  return (
    <Popover>
      <PopoverTrigger asChild>
        {/* Two-line control: the preset on top, the window it resolves to below,
            so the header states the actual period instead of just "12 months". */}
        <button
          type="button"
          className={cn(
            "group flex h-10 items-center gap-2.5 rounded-control border border-hairline bg-surface px-3 text-left",
            "transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          )}
          aria-label={t("Time range")}
        >
          <CalendarClock className="size-4 shrink-0 text-content-dim" />
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-body-s font-bold text-content">{label}</span>
            <span className="tnum block truncate text-body-s text-content-dim">
              {playing || scrubbing ? formatDateTime(headDate) : `${formatDate(start)} – ${formatDate(end)}`}
            </span>
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-content-dim" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="center" className="w-80">
        <div className="space-y-3">
          <div>
            <div className="mb-1.5 text-12 font-semibold text-content-dim">{t("Time range")}</div>
            <div className="flex flex-wrap gap-1">
              {PRESETS.map((p) => (
                <PresetButton
                  key={p.id}
                  active={preset === p.id}
                  onClick={() => setPreset(p.id)}
                  label={t(p.label)}
                />
              ))}
              {preset === "custom" && (
                <span className="rounded-control bg-primary/15 px-2 py-1 text-12 font-medium text-primary">
                  {t("Custom")}
                </span>
              )}
            </div>
          </div>

          <div className="tnum flex items-center justify-between text-12 text-content-dim">
            <span>{formatDate(start)}</span>
            <span>{formatDate(end)}</span>
          </div>

          <Separator />

          {/* Playhead + transport */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-12 font-semibold text-content-dim">{t("Playhead")}</span>
              <span className="tnum text-12 font-medium text-content">{formatDateTime(headDate)}</span>
            </div>
            <Slider
              value={[Math.round(playhead * 100)]}
              min={0}
              max={100}
              step={1}
              onValueChange={([v]) => {
                setPlaying(false);
                setPlayhead(v / 100);
              }}
            />
            <div className="flex items-center gap-1.5">
              <Button variant="secondary" size="sm" onClick={togglePlay} className="gap-1.5">
                {playing ? <Pause /> : <Play />}
                {playing ? t("Pause") : t("Play")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setPlaying(false);
                  setPlayhead(1);
                }}
                className="gap-1.5"
              >
                <RotateCcw /> {t("Now")}
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function PresetButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-control px-2.5 py-1 text-12 font-medium transition-colors",
        active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
      )}
    >
      {label}
    </button>
  );
}
