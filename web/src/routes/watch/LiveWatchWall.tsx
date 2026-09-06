import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  Cctv, Database, Layers, Loader2, Maximize2, Minimize2, ScanEye, Shield, Video,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type {
  CctvAlert, CctvCamera, CctvDispatch, CctvDispatchProposal, CctvResponder,
} from "@/api/endpoints/cctv";
import { cn } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { useUIStore } from "@/stores/useUIStore";
import { districtName, useDisasterStore } from "@/stores/useDisasterStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/common/PageHeader";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { basemapStyle, BASEMAP_OPTIONS, type BasemapId } from "@/components/map/mapConfig";
import { DistrictPicker, KpiTile, Panel } from "@/routes/emergency/erShared";
import { AlertQueueRow, AlertReviewCard } from "@/routes/watch/AlertCard";
import { CameraFeedPanel } from "@/routes/watch/CameraFeedPanel";
import {
  alertCore, alertPulse, cameraMarkers, cameraViewCones, CCTV_LEGEND, dispatchArcs,
  responderMarkers,
} from "@/routes/watch/cctvLayers";
import { formatKm, humanise } from "@/routes/watch/cctvFormat";

/* ============================================================================
   Live Watch Wall — multi-camera video-analytics monitoring with human review
   and nearest-station dispatch.

   The whole surface is built around one claim it must never overstate: the
   analytics PROPOSES, a person DECIDES. So the page always shows, side by side,
   (a) what was detected, (b) how confident the detector was, (c) which detector
   produced it, and (d) the two separate confirmations needed before a unit moves.

   Polling: alerts and cameras refresh on a 20s interval rather than the 120s used
   elsewhere in the app. That is a deliberate deviation — a review queue for
   in-progress street incidents is worthless at two-minute latency — and it is the
   only surface in the product that polls this fast.
   ========================================================================== */

const WALL_REFETCH_MS = 20_000;

// Fallback only. The view is normally FITTED to the cameras actually in scope
// (see the fit effect below) — a hardcoded centre would leave the map blank
// whenever the district filter points somewhere else, which is the worst
// possible first impression for a monitoring wall.
const WALL_VIEW: MapViewState = {
  longitude: 76.2,
  latitude: 14.8,
  zoom: 6.4,
  pitch: 0,
  bearing: 0,
};

const MAX_PINNED_FEEDS = 3;

/** Camera bounding box -> a view that frames the whole estate in scope. */
function fitToCameras(cameras: { lon: number; lat: number }[]): MapViewState | null {
  if (cameras.length === 0) return null;
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const c of cameras) {
    minLon = Math.min(minLon, c.lon);
    maxLon = Math.max(maxLon, c.lon);
    minLat = Math.min(minLat, c.lat);
    maxLat = Math.max(maxLat, c.lat);
  }
  const span = Math.max(maxLon - minLon, maxLat - minLat, 0.008);
  // Approximate the zoom that fits `span` degrees, with a margin so markers are
  // not flush against the edge. Clamped so a single camera does not zoom to the
  // building and a state-wide filter still frames Karnataka.
  const zoom = Math.min(14.5, Math.max(6, Math.log2(360 / span) - 1.35));
  return {
    longitude: (minLon + maxLon) / 2,
    latitude: (minLat + maxLat) / 2,
    zoom,
    pitch: 0,
    bearing: 0,
  };
}

type QueueFilter = "proposed" | "confirmed" | "dispatched" | "all";

const QUEUE_FILTERS: { value: QueueFilter; label: string }[] = [
  { value: "proposed", label: "Needs review" },
  { value: "confirmed", label: "Confirmed" },
  { value: "dispatched", label: "Responding" },
  { value: "all", label: "All" },
];

type Selected =
  | { type: "camera"; camera: CctvCamera }
  | { type: "responder"; responder: CctvResponder }
  | null;

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c] ?? c);
}

/** States plainly what is and is not running, from the server's own report. */
function CapabilityBanner({
  capability,
}: {
  capability?: {
    detector_kind: string;
    detector_label: string;
    runs_frame_inference_in_service: boolean;
    external_ingest_enabled: boolean;
    note: string;
  };
}) {
  if (!capability) return null;
  const synthetic = capability.detector_kind === "synthetic_replay";
  return (
    <div
      className={cn(
        "flex flex-wrap items-start gap-x-3 gap-y-1 rounded-control border px-3 py-2 text-12",
        synthetic
          ? "border-severity-medium/40 bg-severity-medium/10"
          : "border-hairline bg-surface-2/50",
      )}
    >
      <span className="flex items-center gap-1.5 font-medium text-content">
        <ScanEye className="size-3.5" />
        Detection source
      </span>
      <Badge variant={synthetic ? "medium" : "outline"}>
        {humanise(capability.detector_kind)}
      </Badge>
      <span className="font-mono text-11 text-content-dim">{capability.detector_label}</span>
      <p className="w-full text-11 leading-relaxed text-content-dim">{capability.note}</p>
    </div>
  );
}

export function LiveWatchWall() {
  const qc = useQueryClient();
  const { role } = useRole();
  const theme = useUIStore((s) => s.theme);
  const activeDistrict = useDisasterStore((s) => s.activeDistrict);

  const canReview = roleCan(role, "cctv_review");
  const canDispatch = roleCan(role, "cctv_dispatch");
  const canAdmin = roleCan(role, "cctv_admin");

  const [viewState, setViewState] = useState<MapViewState>(WALL_VIEW);
  const [basemap, setBasemap] = useState<BasemapId>("auto");
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("proposed");
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [pinnedCameraIds, setPinnedCameraIds] = useState<number[]>([]);
  const [selected, setSelected] = useState<Selected>(null);
  const [showResponders, setShowResponders] = useState(true);
  const [showCones, setShowCones] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pulse, setPulse] = useState(0);
  // Dispatch proposals returned by a confirmation, kept per alert so the ranked
  // alternatives and the geometry source stay visible after the mutation settles.
  const [proposals, setProposals] = useState<Record<number, CctvDispatchProposal>>({});

  const district = activeDistrict ?? undefined;

  // --- data ---------------------------------------------------------------
  const overviewQ = useQuery({
    queryKey: ["cctv", "overview", district],
    queryFn: ({ signal }) => api.cctv.overview(district, signal),
    refetchInterval: WALL_REFETCH_MS,
  });
  const camerasQ = useQuery({
    queryKey: ["cctv", "cameras", district],
    queryFn: ({ signal }) => api.cctv.cameras({ district_id: district }, signal),
    refetchInterval: WALL_REFETCH_MS,
  });
  const alertsQ = useQuery({
    queryKey: ["cctv", "alerts", district, queueFilter],
    queryFn: ({ signal }) => api.cctv.alerts(
      { district_id: district, status: queueFilter === "all" ? undefined : queueFilter,
        limit: 200 },
      signal,
    ),
    refetchInterval: WALL_REFETCH_MS,
  });
  // The map should show everything live regardless of the queue filter, so it has
  // its own unfiltered read rather than reusing the queue query.
  const mapAlertsQ = useQuery({
    queryKey: ["cctv", "alerts", district, "map"],
    queryFn: ({ signal }) => api.cctv.alerts({ district_id: district, limit: 400 }, signal),
    refetchInterval: WALL_REFETCH_MS,
  });
  const respondersQ = useQuery({
    queryKey: ["cctv", "responders", district],
    queryFn: ({ signal }) => api.cctv.responders({ district_id: district }, signal),
  });
  const dispatchesQ = useQuery({
    queryKey: ["cctv", "dispatch", district],
    queryFn: ({ signal }) => api.cctv.dispatches({ district_id: district, limit: 200 }, signal),
    refetchInterval: WALL_REFETCH_MS,
  });
  const detailQ = useQuery({
    queryKey: ["cctv", "alert", selectedAlertId],
    queryFn: ({ signal }) => api.cctv.alert(selectedAlertId as number, signal),
    enabled: selectedAlertId != null,
  });

  // Memoised so the `?? []` fallback does not allocate a fresh array every render
  // and invalidate the lookup maps + layer memo below on every tick.
  const cameras = useMemo(() => camerasQ.data?.cameras ?? [], [camerasQ.data]);
  const queue = useMemo(() => alertsQ.data?.alerts ?? [], [alertsQ.data]);
  const responders = useMemo(() => respondersQ.data?.responders ?? [], [respondersQ.data]);
  const dispatches = useMemo(() => dispatchesQ.data?.dispatches ?? [], [dispatchesQ.data]);
  const capability = overviewQ.data?.capability;

  // Only unresolved alerts belong on the map; a dismissed one is noise.
  const mapAlerts = useMemo(
    () => (mapAlertsQ.data?.alerts ?? []).filter(
      (a) => a.status === "proposed" || a.status === "confirmed" || a.status === "dispatched",
    ),
    [mapAlertsQ.data],
  );

  const cameraById = useMemo(
    () => new Map(cameras.map((c) => [c.camera_id, c])),
    [cameras],
  );
  const alertById = useMemo(
    () => new Map(mapAlerts.map((a) => [a.cctv_alert_id, a])),
    [mapAlerts],
  );
  const responderById = useMemo(
    () => new Map(responders.map((r) => [r.patrol_unit_id, r])),
    [responders],
  );

  const detail = detailQ.data;
  const selectedAlert = detail?.alert
    ?? queue.find((a) => a.cctv_alert_id === selectedAlertId)
    ?? null;

  // --- mutations ----------------------------------------------------------
  const invalidate = () => qc.invalidateQueries({ queryKey: ["cctv"] });

  const seed = useMutation({
    mutationFn: () => api.cctv.seed(),
    onSuccess: invalidate,
  });
  const runPass = useMutation({
    mutationFn: () => api.cctv.runAnalytics({ district_id: district }),
    onSuccess: invalidate,
  });
  const confirm = useMutation({
    mutationFn: ({ alertId, note }: { alertId: number; note?: string }) =>
      api.cctv.confirmAlert(alertId, { note }),
    onSuccess: (res, vars) => {
      if (res.dispatch_proposal) {
        setProposals((p) => ({ ...p, [vars.alertId]: res.dispatch_proposal! }));
      }
      invalidate();
    },
  });
  const dismiss = useMutation({
    mutationFn: ({ alertId, reason, note }:
                 { alertId: number; reason: string; note?: string }) =>
      api.cctv.dismissAlert(alertId, reason as never, note),
    onSuccess: (_res, vars) => {
      // A dismissed alert leaves the "needs review" queue, so drop the selection
      // rather than leaving a stale card on screen.
      if (selectedAlertId === vars.alertId && queueFilter === "proposed") {
        setSelectedAlertId(null);
      }
      invalidate();
    },
  });
  const propose = useMutation({
    mutationFn: (alertId: number) => api.cctv.proposeDispatch(alertId),
    onSuccess: (res) => {
      setProposals((p) => ({ ...p, [res.cctv_alert_id]: res }));
      invalidate();
    },
  });
  const advance = useMutation({
    mutationFn: ({ dispatchId, status, version }:
                 { dispatchId: number; status: string; version: number }) =>
      api.cctv.transitionDispatch(dispatchId, status as never, { expectedVersion: version }),
    onSuccess: invalidate,
  });

  const mutationError = confirm.error ?? dismiss.error ?? propose.error ?? advance.error;

  // --- frame the map on the cameras actually in scope -----------------------
  // Refits once per district selection. Keyed on the district (not the camera
  // array) so a 20s poll never yanks the view out from under someone who has
  // panned somewhere deliberately.
  const fittedFor = useRef<string | null>(null);
  useEffect(() => {
    const key = String(district ?? "all");
    if (fittedFor.current === key) return;
    const fitted = fitToCameras(cameras);
    if (!fitted) return;
    fittedFor.current = key;
    setViewState(fitted);
  }, [district, cameras]);

  // --- alert pulse (the only looping animation, mirroring the red-zone map) --
  useEffect(() => {
    if (mapAlerts.length === 0) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPulse(0.5);
      return;
    }
    const t = window.setInterval(() => setPulse((p) => (p + 0.04) % 1), 55);
    return () => window.clearInterval(t);
  }, [mapAlerts.length]);

  useEffect(() => {
    if (!isFullscreen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [isFullscreen]);

  // --- interactions -------------------------------------------------------
  /** Show ONE feed: the camera being looked at, replacing whatever was open.
      Selecting a new alert must not leave the previous clip playing — two feeds
      side by side with one review card is ambiguous about which is under review. */
  const focusCamera = (cameraId: number) => setPinnedCameraIds([cameraId]);

  /** Add a feed alongside the current one. Only ever an explicit user action
      (the "Nearby cameras" corroboration list), never a side effect. */
  const addCamera = (cameraId: number) => {
    setPinnedCameraIds((ids) => {
      if (ids.includes(cameraId)) return ids;
      return [...ids, cameraId].slice(-MAX_PINNED_FEEDS);
    });
  };

  const openAlert = (alert: CctvAlert) => {
    setSelectedAlertId(alert.cctv_alert_id);
    focusCamera(alert.camera_id);
    setSelected(null);
    if (alert.lon != null && alert.lat != null) {
      setViewState((v) => ({
        ...v,
        longitude: alert.lon as number,
        latitude: alert.lat as number,
        zoom: Math.max(v.zoom, 14),
      }));
    }
  };

  const layers = useMemo<Layer[]>(() => {
    const L: Layer[] = [];
    if (showCones) L.push(cameraViewCones(cameras));
    if (showResponders) {
      L.push(dispatchArcs(
        dispatches.filter((d) => !["closed", "cancelled"].includes(d.status)),
        alertById, responderById,
      ));
      L.push(responderMarkers(responders, (r) => setSelected({ type: "responder", responder: r })));
    }
    L.push(cameraMarkers(cameras, (c) => {
      setSelected({ type: "camera", camera: c });
      focusCamera(c.camera_id);
    }, selected?.type === "camera" ? selected.camera.camera_id : null));
    if (mapAlerts.length) {
      L.push(alertPulse(mapAlerts, pulse));
      L.push(alertCore(mapAlerts, openAlert));
    }
    return L;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras, responders, dispatches, mapAlerts, pulse, showResponders, showCones,
      selected, alertById, responderById]);

  const getTooltip = (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
    const o = info.object as unknown;
    if (!o) return null;
    let html = "";
    const id = info.layer?.id;
    if (id === "cctv-cameras") {
      const c = o as CctvCamera;
      html = `${c.name} · ${c.status}`
        + (c.open_alert_count ? ` · ${c.open_alert_count} open alert(s)` : "")
        + (c.analytics_enabled ? "" : " · analytics off");
    } else if (id === "cctv-alert-core") {
      const a = o as CctvAlert;
      html = `${a.severity.toUpperCase()} · ${a.title} · ${Math.round(a.confidence * 100)}% confident`;
    } else if (id === "cctv-responders") {
      const r = o as CctvResponder;
      html = `${r.name} · ${humanise(r.kind)} · ${r.status}`;
    }
    if (!html) return null;
    return {
      html: escapeHtml(html),
      style: {
        background: "#1d2740", color: "#e8ecf6", fontSize: "12px",
        padding: "4px 8px", borderRadius: "8px", border: "1px solid #28324d",
      },
    };
  };

  const ov = overviewQ.data;
  const estateEmpty = ov != null && ov.cameras.total === 0;
  const pinned = pinnedCameraIds
    .map((id) => cameraById.get(id))
    .filter((c): c is CctvCamera => c != null);

  const detailDispatches: CctvDispatch[] = detail?.dispatches
    ?? (selectedAlertId != null
      ? dispatches.filter((d) => d.cctv_alert_id === selectedAlertId)
      : []);

  return (
    <div className={cn(isFullscreen && "fixed inset-0 z-[80] flex min-h-0 flex-col overflow-auto bg-bg p-3")}>
      <PageHeader
        title="Live Watch Wall"
        description={`CCTV video analytics — ${districtName(activeDistrict)}`}
        info={
          <div className="space-y-1.5">
            <p>
              Cameras are watched for a fixed set of incident classes. The analytics
              only <strong>proposes</strong> an alert.
            </p>
            <p>
              An analyst confirms or dismisses it, and dispatching the nearest
              responder is a second, separately-confirmed decision. Nothing on this
              page dispatches automatically.
            </p>
          </div>
        }
        actions={
          <>
            <DistrictPicker />
            {canReview && (
              <Button size="sm" variant="outline" disabled={runPass.isPending}
                      onClick={() => runPass.mutate()}
                      title="Run one analysis pass over the enabled cameras">
                {runPass.isPending ? <Loader2 className="animate-spin" /> : <ScanEye />}
                Run analysis pass
              </Button>
            )}
            {canAdmin && (
              <Button size="sm" variant={estateEmpty ? "primary" : "outline"}
                      disabled={seed.isPending} onClick={() => seed.mutate()}>
                {seed.isPending ? <Loader2 className="animate-spin" /> : <Database />}
                Seed camera estate
              </Button>
            )}
          </>
        }
      />

      {overviewQ.isError && (
        <p className="mb-3 text-13 text-severity-critical">{errorMessage(overviewQ.error)}</p>
      )}
      {seed.isError && (
        <p className="mb-3 text-12 text-severity-critical">{errorMessage(seed.error)}</p>
      )}
      {runPass.isError && (
        <p className="mb-3 text-12 text-severity-critical">{errorMessage(runPass.error)}</p>
      )}
      {runPass.data && (
        <p className="mb-3 text-11 text-content-dim">
          Analysed {runPass.data.cameras_analysed} camera
          {runPass.data.cameras_analysed === 1 ? "" : "s"}:{" "}
          {runPass.data.alerts_proposed} alert
          {runPass.data.alerts_proposed === 1 ? "" : "s"} proposed,{" "}
          {runPass.data.detections_suppressed} duplicate detection
          {runPass.data.detections_suppressed === 1 ? "" : "s"} suppressed,{" "}
          {runPass.data.below_alert_threshold} below the alert threshold.
        </p>
      )}

      <div className="mb-4">
        <CapabilityBanner capability={capability} />
      </div>

      {/* readiness KPIs */}
      {ov && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <KpiTile
            label="Cameras watched"
            value={`${ov.cameras.analytics_enabled}/${ov.cameras.total}`}
            tone={ov.cameras.analytics_enabled ? "good" : "neutral"}
            hint={ov.cameras.offline ? `${ov.cameras.offline} offline` : undefined}
            info="Cameras with analytics enabled, out of the registered estate. An offline or in-maintenance camera produces no frames and is never analysed, so it can raise no alerts."
          />
          <KpiTile
            label="Awaiting review"
            value={ov.pending_review}
            tone={ov.pending_review ? "critical" : "good"}
            info="Proposed alerts no one has judged yet. Each one needs a human to confirm or dismiss it before any response can follow."
          />
          <KpiTile
            label="Low confidence"
            value={ov.low_confidence_pending}
            tone={ov.low_confidence_pending ? "warn" : "neutral"}
            hint="in the review queue"
            info="Pending alerts whose detector confidence fell below the escalation threshold. They are surfaced rather than hidden, and are the ones most worth watching on the feed before deciding."
          />
          <KpiTile
            label="Confirmed"
            value={ov.confirmed_awaiting_dispatch}
            tone={ov.confirmed_awaiting_dispatch ? "warn" : "neutral"}
            hint="no unit sent yet"
            info="Alerts a human has confirmed as real but for which no responder has been dispatched. Confirming and dispatching are deliberately separate decisions."
          />
          <KpiTile
            label="Responding"
            value={ov.dispatched_active}
            info="Alerts with a responder currently dispatched, acknowledged, en route or on scene."
          />
          <KpiTile
            label="Dismissed 24h"
            value={ov.dismissed_today}
            info="Alerts dismissed in the last 24 hours, with a recorded reason. This is the detector's false-positive trail — the honest counterweight to the detection count."
          />
        </div>
      )}

      {estateEmpty && (
        <Panel className="mb-4">
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Cctv className="size-8 text-content-dim" />
            <p className="text-14 text-content">No cameras registered yet.</p>
            {canAdmin
              ? <p className="text-12 text-content-dim">
                  Use “Seed camera estate” to load the synthetic Karnataka junction
                  cameras and responders.
                </p>
              : <p className="text-12 text-content-dim">
                  Ask an administrator to register the camera estate.
                </p>}
          </div>
        </Panel>
      )}

      <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_26rem]">
        {/* --- map + floating feeds --- */}
        <div
          className={cn(
            "relative overflow-hidden rounded-card border border-hairline",
            isFullscreen ? "min-h-0 flex-1" : "h-[38rem]",
          )}
        >
          <MapCanvas
            viewState={viewState}
            onViewStateChange={setViewState}
            layers={layers}
            getTooltip={getTooltip}
            mapStyle={basemapStyle(basemap, theme)}
          />

          {/* pinned live feeds — the floating video windows over the map */}
          {pinned.length > 0 && (
            <div className="pointer-events-none absolute inset-x-3 top-3 z-20 flex flex-wrap justify-end gap-2">
              {pinned.map((cam) => {
                // A busy camera can carry several open alerts. When the analyst has
                // one selected on this camera, the tile must caption THAT alert —
                // otherwise the strip and the review card disagree about what is
                // being looked at, which is the one thing this tile cannot do.
                const camAlert =
                  (selectedAlert && selectedAlert.camera_id === cam.camera_id
                    ? selectedAlert
                    : undefined)
                  ?? mapAlerts.find(
                    (a) => a.camera_id === cam.camera_id
                      && (a.status === "proposed" || a.status === "confirmed"
                        || a.status === "dispatched"),
                  );
                const showingDetail = camAlert
                  && detail?.alert.cctv_alert_id === camAlert.cctv_alert_id;
                return (
                  <div key={cam.camera_id} className="pointer-events-auto">
                    <CameraFeedPanel
                      camera={cam}
                      boxes={showingDetail ? detail?.detection?.boxes : undefined}
                      // The panel only draws boxes it can trust against these
                      // pixels; synthetic geometry is suppressed there.
                      detectorKind={showingDetail ? detail?.detection?.detector_kind : undefined}
                      severity={camAlert?.severity}
                      detectionLabel={camAlert?.title}
                      ageSeconds={camAlert?.age_seconds}
                      onClose={() => setPinnedCameraIds((ids) =>
                        ids.filter((id) => id !== cam.camera_id))}
                      onOpenDetail={camAlert ? () => openAlert(camAlert) : undefined}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {/* left control card */}
          <div className="absolute bottom-3 left-3 z-10 max-h-[calc(100%-1.5rem)] w-56 overflow-y-auto rounded-card border border-hairline bg-surface/95 p-3 shadow-pop backdrop-blur">
            <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold text-content-dim">
              <Layers className="size-3.5" /> Map view
            </div>
            <NativeSelect
              value={basemap}
              onChange={(v) => setBasemap(v as BasemapId)}
              options={BASEMAP_OPTIONS.map((b) => ({ value: b.id, label: b.label }))}
              placeholder="Match theme"
              aria-label="Basemap"
              className="mb-2"
            />
            <div className="mb-2 grid gap-1">
              <button
                type="button"
                onClick={() => setShowResponders((s) => !s)}
                aria-pressed={showResponders}
                className={cn(
                  "flex items-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors",
                  showResponders
                    ? "bg-primary text-primary-fg"
                    : "bg-surface-2 text-content-dim hover:text-content",
                )}
              >
                <Shield className="size-3.5" /> Responders
              </button>
              <button
                type="button"
                onClick={() => setShowCones((s) => !s)}
                aria-pressed={showCones}
                className={cn(
                  "flex items-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors",
                  showCones
                    ? "bg-primary text-primary-fg"
                    : "bg-surface-2 text-content-dim hover:text-content",
                )}
              >
                <Video className="size-3.5" /> Coverage cones
              </button>
            </div>
            <ul className="space-y-0.5 border-t border-hairline pt-2">
              {CCTV_LEGEND.map((item) => (
                <li key={item.label} className="flex items-center gap-1.5 text-11 text-content-dim">
                  <span className="size-2 shrink-0 rounded-full"
                        style={{ background: item.color }} aria-hidden="true" />
                  <span className="truncate">{item.label}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* fullscreen toggle */}
          <button
            type="button"
            onClick={() => setIsFullscreen((v) => !v)}
            className="absolute right-3 top-3 z-10 inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface/95 px-2.5 py-1.5 text-12 font-medium text-content shadow-pop backdrop-blur transition-colors hover:bg-surface-2"
            aria-label={isFullscreen ? "Exit full screen wall" : "Open full screen wall"}
            title={isFullscreen ? "Exit full screen (Esc)" : "Open full screen"}
          >
            {isFullscreen ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>

          {/* selected camera / responder readout */}
          {selected && (
            <div className="absolute bottom-3 right-3 z-10 w-64 rounded-card border border-hairline bg-surface/95 p-3 shadow-pop backdrop-blur">
              {selected.type === "camera" ? (
                <>
                  <p className="text-13 font-semibold text-content">{selected.camera.name}</p>
                  <p className="mt-0.5 font-mono text-11 text-content-dim">
                    {selected.camera.code}
                  </p>
                  <p className="mt-1 text-11 text-content-dim">
                    {selected.camera.location_label ?? "—"}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge variant={selected.camera.status === "online" ? "low" : "medium"}>
                      {selected.camera.status}
                    </Badge>
                    {selected.camera.analytics_enabled
                      ? <Badge variant="outline">analytics on</Badge>
                      : <Badge variant="neutral">analytics off</Badge>}
                    {selected.camera.open_alert_count > 0 && (
                      <Badge variant="critical">
                        {selected.camera.open_alert_count} open
                      </Badge>
                    )}
                  </div>
                  {selected.camera.detector_profile && (
                    <p className="mt-2 text-11 text-content-dim">
                      Watched for: {selected.camera.detector_profile.split(",")
                        .map((s) => humanise(s.trim())).join(", ")}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="text-13 font-semibold text-content">
                    {selected.responder.name}
                  </p>
                  <p className="mt-0.5 font-mono text-11 text-content-dim">
                    {selected.responder.code}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge variant="outline">{humanise(selected.responder.kind)}</Badge>
                    <Badge variant={selected.responder.status === "available" ? "low" : "medium"}>
                      {selected.responder.status}
                    </Badge>
                  </div>
                  {selected.responder.capabilities.length > 0 && (
                    <p className="mt-2 text-11 text-content-dim">
                      {selected.responder.capabilities.map(humanise).join(", ")}
                    </p>
                  )}
                </>
              )}
              <Button size="sm" variant="ghost" className="mt-2"
                      onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          )}
        </div>

        {/* --- queue + review --- */}
        <div className="flex min-w-0 flex-col gap-4">
          <Panel
            title="AI alerts"
            actions={
              <NativeSelect
                aria-label="Alert queue filter"
                value={queueFilter}
                onChange={(v) => setQueueFilter((v || "proposed") as QueueFilter)}
                options={QUEUE_FILTERS.map((f) => ({ value: f.value, label: f.label }))}
                placeholder="Needs review"
                className="w-36"
              />
            }
          >
            {alertsQ.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
            {alertsQ.isError && (
              <p className="text-12 text-severity-critical">{errorMessage(alertsQ.error)}</p>
            )}
            <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {queue.map((a) => (
                <AlertQueueRow
                  key={a.cctv_alert_id}
                  alert={a}
                  active={a.cctv_alert_id === selectedAlertId}
                  onSelect={() => openAlert(a)}
                />
              ))}
              {!alertsQ.isLoading && queue.length === 0 && (
                <li className="py-4 text-center text-12 text-content-dim">
                  {queueFilter === "proposed"
                    ? "Nothing awaiting review."
                    : "No alerts in this state."}
                </li>
              )}
            </ul>
          </Panel>

          <Panel title="Alert review">
            {selectedAlert ? (
              <AlertReviewCard
                alert={selectedAlert}
                dispatches={detailDispatches}
                proposal={proposals[selectedAlert.cctv_alert_id]}
                canReview={canReview}
                canDispatch={canDispatch}
                confirming={confirm.isPending}
                dismissing={dismiss.isPending}
                dispatching={propose.isPending || advance.isPending}
                errorText={mutationError ? errorMessage(mutationError) : null}
                onConfirm={(note) =>
                  confirm.mutate({ alertId: selectedAlert.cctv_alert_id, note })}
                onDismiss={(reason, note) =>
                  dismiss.mutate({ alertId: selectedAlert.cctv_alert_id, reason, note })}
                onPropose={() => propose.mutate(selectedAlert.cctv_alert_id)}
                onAdvanceDispatch={(d, next) =>
                  advance.mutate({ dispatchId: d.cctv_dispatch_id, status: next,
                                   version: d.version })}
                onFocusMap={selectedAlert.lon != null
                  ? () => setViewState((v) => ({
                      ...v,
                      longitude: selectedAlert.lon as number,
                      latitude: selectedAlert.lat as number,
                      zoom: Math.max(v.zoom, 15),
                    }))
                  : undefined}
              />
            ) : (
              <p className="py-6 text-center text-12 text-content-dim">
                Select an alert to review the feed, the detection and the nearest
                responder.
              </p>
            )}
          </Panel>

          {/* corroborating cameras for the selected alert */}
          {detail && detail.nearby_cameras.length > 0 && (
            <Panel title="Nearby cameras">
              <p className="mb-2 text-11 text-content-dim">
                Within 1.5 km of this alert — open one to corroborate before deciding.
              </p>
              <ul className="space-y-1">
                {detail.nearby_cameras.map((c) => (
                  <li key={c.camera_id}>
                    <button
                      type="button"
                      onClick={() => addCamera(c.camera_id)}
                      className="flex w-full items-center gap-2 rounded-control border border-hairline px-2.5 py-1.5 text-left text-12 transition-colors hover:bg-surface-2"
                    >
                      <Video className="size-3.5 shrink-0 text-content-dim" />
                      <span className="min-w-0 flex-1 truncate text-content">{c.name}</span>
                      <span className="shrink-0 text-11 text-content-dim">
                        {detail.alert.lon != null
                          ? formatKm(haversineKm(
                              detail.alert.lon, detail.alert.lat as number, c.lon, c.lat))
                          : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>

      <p className="mt-4 text-11 text-content-dim">
        Synthetic hackathon decision-support demonstration — not an official
        surveillance, alerting or dispatch system. Detections describe a scene, never
        a person; no detection becomes an alert or a dispatch without a recorded
        human confirmation.
      </p>
    </div>
  );
}

/** Local great-circle distance for the "nearby cameras" read-out. */
function haversineKm(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const R = 6371.0088;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}
