import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  Box,
  Building2,
  Camera,
  Flame,
  Layers,
  MapPin,
  Maximize2,
  Minimize2,
  Radar,
  Share2,
  Shapes,
  Shield,
  Siren,
} from "lucide-react";
import { api } from "@/api";
import type { AlertFeature, CaseLinkNode, MapCell, PointFeature, StationFeature } from "@/api/types";
import { cn, formatNumber } from "@/lib/utils";
import { categoryColor } from "@/lib/palette";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { useTimeStore } from "@/stores/useTimeStore";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { Badge } from "@/components/ui/badge";
import { NativeSelect } from "@/components/ui/native-select";
import { ExportViewButton, PrintHeader } from "@/components/common/PrintExport";
import { Layer as MlLayer, Marker, Source } from "react-map-gl/maplibre";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { basemapStyle, BASEMAP_OPTIONS, KARNATAKA_VIEW, type BasemapId } from "@/components/map/mapConfig";
import { StreetViewPanel } from "@/components/map/StreetViewPanel";
import { CasePopup, StationPopup } from "@/components/map/MapDetailPopup";
import { hasMapillary, MAPILLARY_TILES } from "@/components/map/mapillary";
import {
  alertCore,
  alertPulse,
  caseArcs,
  coverageGaps,
  densityHeatmap,
  districtBoundaries,
  districtSymbols,
  forecastCells,
  hexBins3D,
  hexColorDomain,
  hotspotOutlines,
  linkSource,
  linkTargets,
  pointsHex,
  pointsScatter,
  shoRegionsLayer,
  stateBoundary,
  stationMarkers,
  talukBoundaries,
  type DistrictAgg,
} from "@/components/map/layers";

type Mode = "live" | "hotspots" | "forecast" | "patrol" | "alerts";
const MODES: { key: Mode; label: string; icon: React.ElementType }[] = [
  { key: "live", label: "Live Map", icon: MapPin },
  { key: "hotspots", label: "Hotspots", icon: Flame },
  { key: "forecast", label: "Forecast", icon: Radar },
  { key: "patrol", label: "Patrol Planning", icon: Shield },
  { key: "alerts", label: "Red-Zone Alerts", icon: Siren },
];

const TOD_BUCKETS: { key: string; label: string; range: [number, number] | null }[] = [
  { key: "all", label: "All day", range: null },
  { key: "night", label: "Night 0–6", range: [0, 6] },
  { key: "morning", label: "Morning 6–12", range: [6, 12] },
  { key: "afternoon", label: "Noon 12–18", range: [12, 18] },
  { key: "evening", label: "Evening 18–24", range: [18, 24] },
];

const HORIZONS = [7, 14, 30];
const STATION_MIN_ZOOM = 7;

type BoundaryKey = "state" | "districts" | "taluks" | "sho";
const BOUNDARY_TOGGLES: { key: BoundaryKey; label: string; swatch: string; aggregateSafe: boolean }[] = [
  { key: "state", label: "State", swatch: "#f59e0b", aggregateSafe: true },
  { key: "districts", label: "Districts", swatch: "#38bdf8", aggregateSafe: true },
  { key: "taluks", label: "Taluks", swatch: "#94a3b8", aggregateSafe: true },
  { key: "sho", label: "SHO regions", swatch: "#60a5fa", aggregateSafe: false },
];

type Selected =
  | { type: "case"; id: number; lon: number; lat: number; approximate: boolean }
  | { type: "station"; station: StationFeature }
  | null;

function caseReferenceLabel(caseId: number, crimeNo?: string | null): string {
  const presentationNumber = crimeNo?.trim();
  return presentationNumber ? `Case ${presentationNumber}` : `Internal case ID #${caseId}`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

function isApproximateLocation(location: {
  not_exact_incident_scene?: boolean | null;
  location_precision?: string | null;
}): boolean {
  return location.not_exact_incident_scene === true
    || location.location_precision === "approximate_locality_reference";
}

function isApproximateLinkSource(source: {
  source_not_exact_incident_scene?: boolean | null;
  source_location_precision?: string | null;
}): boolean {
  return source.source_not_exact_incident_scene === true
    || source.source_location_precision === "approximate_locality_reference";
}

function haversineKm(a: [number, number], b: [number, number]) {
  const R = 6371;
  const dLat = ((b[1] - a[1]) * Math.PI) / 180;
  const dLon = ((b[0] - a[0]) * Math.PI) / 180;
  const la1 = (a[1] * Math.PI) / 180;
  const la2 = (b[1] * Math.PI) / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

export function MapHotspots() {
  const { role } = useRole();
  const push = usePeekStore((s) => s.push);
  const playhead = useTimeStore((s) => s.playhead);
  const theme = useUIStore((s) => s.theme);
  // District-aggregate-only seat (no point-level pins). INTERIM: none are,
  // mirroring geo/router.py POINT_LEVEL_DENY.
  const aggregateOnly = !roleCan(role, "case_read");

  const [viewState, setViewState] = useState<MapViewState>(KARNATAKA_VIEW);
  const [mode, setMode] = useState<Mode>(aggregateOnly ? "forecast" : "live");
  const [tod, setTod] = useState("all");
  const [horizon, setHorizon] = useState(30);
  const [crimeFilter, setCrimeFilter] = useState("");
  const [showStations, setShowStations] = useState(true);
  const [ackIds, setAckIds] = useState<Set<number>>(new Set());
  const [pulse, setPulse] = useState(0);
  const [selected, setSelected] = useState<Selected>(null);
  const [streetView, setStreetView] = useState<{ lon: number; lat: number } | null>(null);
  const [svCamera, setSvCamera] = useState<{ lon: number; lat: number } | null>(null);
  const [showCoverage, setShowCoverage] = useState(false);
  // 3D + basemap + connections
  const [basemap, setBasemap] = useState<BasemapId>("auto");
  const [is3D, setIs3D] = useState(false);
  const [hex3D, setHex3D] = useState(false);
  const [showLinks, setShowLinks] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [linkHub, setLinkHub] = useState<{ id: number; lon: number; lat: number } | null>(null);
  // optional admin boundary overlays (state / district / taluk / SHO regions)
  const [boundaries, setBoundaries] = useState<Set<BoundaryKey>>(() => new Set());
  const toggleBoundary = (k: BoundaryKey) =>
    setBoundaries((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const allowedModes = aggregateOnly ? MODES.filter((m) => m.key === "forecast") : MODES;

  const mapStyle = basemapStyle(basemap, theme);

  useEffect(() => {
    if (!isFullscreen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isFullscreen]);

  const set3D = (on: boolean) => {
    setIs3D(on);
    setViewState((v) => ({ ...v, pitch: on ? 50 : 0, bearing: on ? v.bearing : 0 }));
  };

  // The only looping animation in the product: red-zone pulse.
  useEffect(() => {
    if (mode !== "alerts") return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPulse(0.5);
      return;
    }
    const t = window.setInterval(() => setPulse((p) => (p + 0.04) % 1), 55);
    return () => window.clearInterval(t);
  }, [mode]);
  useEffect(() => setSelected(null), [mode]);

  // --- data. NB: incidents/hotspots are NOT constrained by the global time
  // window (the dataset spans 2021–2025; a "last 30 days" window would be empty).
  // The scrubber's playhead instead animates over the data's OWN date range. ---
  const needPoints = mode === "live" || mode === "hotspots";
  const pointsQ = useQuery({
    queryKey: ["geo", "points", "all"],
    queryFn: ({ signal }) => api.geo.points({ limit: 12000 }, signal),
    enabled: needPoints && !aggregateOnly,
  });
  const stationsQ = useQuery({
    queryKey: ["geo", "stations"],
    queryFn: ({ signal }) => api.geo.stations({ limit: 1500 }, signal),
    enabled: mode === "live" && !aggregateOnly,
  });
  const hotspotsQ = useQuery({
    queryKey: ["geo", "hotspots", "map"],
    queryFn: ({ signal }) => api.geo.hotspots({ limit: 1500 }, signal),
    enabled: mode === "hotspots" || mode === "patrol",
  });
  const forecastQ = useQuery({
    queryKey: ["forecast", "map", "fused"],
    queryFn: ({ signal }) => api.forecast.map({ layer: "fused" }, signal),
    enabled: mode === "forecast" || mode === "patrol",
  });
  const alertsQ = useQuery({
    queryKey: ["geo", "alerts", "map"],
    queryFn: ({ signal }) => api.geo.alerts({ limit: 300 }, signal),
    enabled: mode === "alerts",
  });
  const linksQ = useQuery({
    queryKey: ["geo", "case-links", linkHub?.id],
    queryFn: ({ signal }) => api.geo.caseLinks(linkHub!.id, 80, signal),
    enabled: mode === "live" && showLinks && linkHub != null,
  });

  // The case-links response is authoritative for source precision. If it marks
  // the selected hub as approximate, close and disable exact-location imagery.
  useEffect(() => {
    const source = linksQ.data;
    if (!source || selected?.type !== "case" || selected.id !== source.source_case_id) return;
    const approximate = isApproximateLinkSource(source);
    if (selected.approximate !== approximate) setSelected({ ...selected, approximate });
    if (approximate) {
      setStreetView(null);
      setSvCamera(null);
    }
  }, [linksQ.data, selected]);

  // Boundary overlays are static reference geography — fetch once, keep forever.
  const stateBndQ = useQuery({
    queryKey: ["geo", "boundary", "state"],
    queryFn: ({ signal }) => api.geo.boundaries("state", signal),
    enabled: boundaries.has("state"),
    staleTime: Infinity,
  });
  const distBndQ = useQuery({
    queryKey: ["geo", "boundary", "districts"],
    queryFn: ({ signal }) => api.geo.boundaries("districts", signal),
    enabled: boundaries.has("districts"),
    staleTime: Infinity,
  });
  const talukBndQ = useQuery({
    queryKey: ["geo", "boundary", "taluks"],
    queryFn: ({ signal }) => api.geo.boundaries("taluks", signal),
    enabled: boundaries.has("taluks"),
    staleTime: Infinity,
  });
  const shoBndQ = useQuery({
    queryKey: ["geo", "sho-regions"],
    queryFn: ({ signal }) => api.geo.shoRegions(1500, signal),
    enabled: boundaries.has("sho") && !aggregateOnly,
    staleTime: Infinity,
  });
  // Persisted boundary versions/counts (data freshness) — the map overlays and
  // the DB share ONE versioned source of truth (JurisdictionBoundary).
  const bndFreshnessQ = useQuery({
    queryKey: ["geo", "jurisdiction", "freshness"],
    queryFn: ({ signal }) => api.geo.jurisdictionFreshness(signal),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  useEffect(() => {
    if (!showLinks) setLinkHub(null);
  }, [showLinks]);

  const allPoints = pointsQ.data?.points ?? [];

  // Distinct crime types actually present (drives the filter + legend).
  const crimeGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of allPoints) if (p.crime_group) counts.set(p.crime_group, (counts.get(p.crime_group) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([g]) => g);
  }, [allPoints]);

  // Playhead → reveal incidents up to a cutoff within the data's own range.
  const dataRange = useMemo<[number, number] | null>(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const p of allPoints) {
      if (!p.date) continue;
      const t = new Date(p.date).getTime();
      if (t < min) min = t;
      if (t > max) max = t;
    }
    return Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null;
  }, [allPoints]);

  const windowPoints = useMemo(() => {
    if (playhead >= 0.999 || !dataRange) return allPoints;
    const cutoff = dataRange[0] + (dataRange[1] - dataRange[0]) * playhead;
    return allPoints.filter((p) => !p.date || new Date(p.date).getTime() <= cutoff);
  }, [allPoints, playhead, dataRange]);

  const visiblePoints = useMemo(
    () => (crimeFilter ? windowPoints.filter((p) => p.crime_group === crimeFilter) : windowPoints),
    [windowPoints, crimeFilter],
  );

  // Governed records remain visible as individual live-map references, but do
  // not contribute to density, hex-bin, hotspot, or other derived aggregates.
  const analyticsVisiblePoints = useMemo(
    () => visiblePoints.filter((p) => !p.excluded_from_derived_analytics),
    [visiblePoints],
  );

  const todPoints = useMemo(() => {
    const bucket = TOD_BUCKETS.find((b) => b.key === tod);
    if (!bucket?.range) return analyticsVisiblePoints;
    const [lo, hi] = bucket.range;
    return analyticsVisiblePoints.filter((p) => p.hour != null && p.hour >= lo && p.hour < hi);
  }, [analyticsVisiblePoints, tod]);

  // Clamped colour domains so the extreme metro outlier can't collapse the ramp
  // (Live low-zoom hex + Hotspots 3D hex both use quantize over these domains).
  const liveHexDomain = useMemo(() => hexColorDomain(analyticsVisiblePoints), [analyticsVisiblePoints]);
  const hotspotHexDomain = useMemo(() => hexColorDomain(todPoints), [todPoints]);

  const stations = stationsQ.data?.stations ?? [];

  const districtAggs = useMemo<DistrictAgg[]>(() => {
    const cells = forecastQ.data?.cells ?? [];
    const by = new Map<number, { lon: number; lat: number; pred: number; conf: number; n: number }>();
    for (const c of cells) {
      if (c.district_id == null || c.lat == null || c.lon == null) continue;
      const cur = by.get(c.district_id) ?? { lon: 0, lat: 0, pred: 0, conf: 0, n: 0 };
      cur.lon += c.lon;
      cur.lat += c.lat;
      cur.pred += c.predicted_count ?? 0;
      cur.conf += c.confidence ?? 0;
      cur.n += 1;
      by.set(c.district_id, cur);
    }
    return [...by.entries()].map(([district_id, v]) => ({
      district_id,
      lon: v.lon / v.n,
      lat: v.lat / v.n,
      predicted: v.pred,
      confidence: v.conf / v.n,
    }));
  }, [forecastQ.data]);

  const gaps = useMemo(() => {
    const cells = (forecastQ.data?.cells ?? []).filter((c) => c.lat != null && c.lon != null);
    if (!cells.length) return [];
    const sorted = [...cells].sort((a, b) => (b.predicted_count ?? 0) - (a.predicted_count ?? 0));
    const top = sorted.slice(0, Math.ceil(sorted.length * 0.25));
    const centroids = (hotspotsQ.data?.hotspots ?? [])
      .filter((h) => h.centroid_lon != null && h.centroid_lat != null)
      .map((h) => [h.centroid_lon as number, h.centroid_lat as number] as [number, number]);
    return top
      .filter((c) => {
        const p: [number, number] = [c.lon as number, c.lat as number];
        return !centroids.some((h) => haversineKm(p, h) < 3);
      })
      .map((c) => ({ lon: c.lon as number, lat: c.lat as number, predicted: c.predicted_count ?? 0 }));
  }, [forecastQ.data, hotspotsQ.data]);

  const activeAlerts = (alertsQ.data?.alerts ?? []).filter((a) => !ackIds.has(a.alert_id));
  const horizonScale = horizon / 30;
  const hasApproximateLocations = mode === "live" && (
    visiblePoints.some((point) => isApproximateLocation(point))
    || (showLinks && linksQ.data != null && (
      isApproximateLinkSource(linksQ.data)
      || linksQ.data.links.some((link) => isApproximateLocation(link))
    ))
  );

  const layers = useMemo<Layer[]>(() => {
    const L: Layer[] = [];
    // Optional boundary overlays, drawn first so they sit beneath the data.
    if (boundaries.has("sho") && shoBndQ.data) L.push(shoRegionsLayer(shoBndQ.data));
    if (boundaries.has("taluks") && talukBndQ.data) L.push(talukBoundaries(talukBndQ.data));
    if (boundaries.has("districts") && distBndQ.data) L.push(districtBoundaries(distBndQ.data));
    if (boundaries.has("state") && stateBndQ.data) L.push(stateBoundary(stateBndQ.data));
    if (aggregateOnly) {
      L.push(districtSymbols(districtAggs, horizonScale));
      return L;
    }
    if (mode === "live") {
      const onCaseClick = (p: PointFeature) => {
        setSelected({
          type: "case", id: p.case_id, lon: p.lon, lat: p.lat,
          approximate: isApproximateLocation(p),
        });
        if (isApproximateLocation(p)) {
          setStreetView(null);
          setSvCamera(null);
        }
        if (showLinks) {
          setLinkHub({ id: p.case_id, lon: p.lon, lat: p.lat });
          if (!is3D) set3D(true);
        }
      };
      if (viewState.zoom < 8.5) L.push(pointsHex(analyticsVisiblePoints, liveHexDomain));
      else L.push(pointsScatter(visiblePoints, onCaseClick));
      if (showStations && viewState.zoom >= STATION_MIN_ZOOM)
        L.push(stationMarkers(stations, (s) => setSelected({ type: "station", station: s })));
      // Connected-cases 3D arcs (shared accused footprint)
      const lk = linksQ.data;
      if (showLinks && linkHub && lk && lk.source_lon != null && lk.source_lat != null) {
        const src = {
          lon: lk.source_lon,
          lat: lk.source_lat,
          not_exact_incident_scene: isApproximateLinkSource(lk),
          location_precision: lk.source_location_precision,
          uncertainty_radius_m: lk.source_uncertainty_radius_m,
        };
        L.push(caseArcs(src, lk.links));
        L.push(
          linkTargets(lk.links, (l: CaseLinkNode) => {
            const approximate = isApproximateLocation(l);
            setSelected({ type: "case", id: l.case_id, lon: l.lon, lat: l.lat, approximate });
            if (approximate) {
              setStreetView(null);
              setSvCamera(null);
            }
            setLinkHub({ id: l.case_id, lon: l.lon, lat: l.lat });
          }),
        );
        L.push(linkSource(src));
      }
    } else if (mode === "hotspots") {
      if (hex3D) {
        L.push(hexBins3D(todPoints, true, hotspotHexDomain));
      } else {
        L.push(densityHeatmap(todPoints));
        if (hotspotsQ.data) L.push(hotspotOutlines(hotspotsQ.data.hotspots));
      }
    } else if (mode === "forecast") {
      L.push(forecastCells(forecastQ.data?.cells ?? [], horizonScale));
      L.push(districtSymbols(districtAggs, horizonScale));
    } else if (mode === "patrol") {
      L.push(forecastCells(forecastQ.data?.cells ?? [], horizonScale));
      L.push(coverageGaps(gaps));
    } else if (mode === "alerts") {
      L.push(alertPulse(activeAlerts, pulse));
      L.push(
        alertCore(activeAlerts, (a) =>
          push({ kind: "alert", id: a.alert_id, label: a.title, sublabel: a.district_name ?? a.alert_type }),
        ),
      );
    }
    return L;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, aggregateOnly, visiblePoints, analyticsVisiblePoints, todPoints, liveHexDomain, hotspotHexDomain, stations, showStations, hotspotsQ.data, forecastQ.data, districtAggs, gaps, activeAlerts, pulse, horizonScale, viewState.zoom, hex3D, showLinks, linkHub, linksQ.data, is3D, boundaries, stateBndQ.data, distBndQ.data, talukBndQ.data, shoBndQ.data]);

  const getTooltip = (info: PickingInfo): { html: string; style: Record<string, string> } | null => {
    // Once a detail popup is open it becomes the single source of information
    // for that marker. Hiding the hover label prevents the duplicate dark
    // tooltip from sitting underneath the popup action, as seen in the prior UI.
    if (selected) return null;
    const o = info.object as unknown;
    if (!o) return null;
    let html = "";
    const id = info.layer?.id;
    if (id === "incident-points") {
      const point = o as PointFeature;
      html = `${point.crime_group ?? "Incident"} · ${caseReferenceLabel(point.case_id, point.crime_no)}`
        + (isApproximateLocation(point) ? " · approximate locality, not exact incident scene" : "");
    }
    else if (id === "incident-hex") html = `${(o as { points?: unknown[] }).points?.length ?? ""} incidents`;
    else if (id === "police-stations") html = `${(o as StationFeature).name ?? "Station"} · ${(o as StationFeature).case_count} cases`;
    else if (id === "link-targets") {
      const link = o as CaseLinkNode;
      html = `${caseReferenceLabel(link.case_id, link.crime_no)} · linked via ${link.via ?? "shared accused"}`
        + (isApproximateLocation(link) ? " · approximate locality, not exact incident scene" : "")
        + (link.location_label ? ` · ${link.location_label}` : "");
    }
    else if (id === "hotspot-hex-3d") html = `${(o as { points?: unknown[] }).points?.length ?? ""} incidents`;
    else if (id === "forecast-cells") html = `~${Math.round(((o as MapCell).predicted_count ?? 0) * horizonScale)} predicted · ${Math.round(((o as MapCell).confidence ?? 0) * 100)}% conf`;
    else if (id === "district-symbols") html = `District ${(o as DistrictAgg).district_id} · ~${Math.round((o as DistrictAgg).predicted * horizonScale)} predicted`;
    else if (id === "coverage-gaps") html = `Coverage gap · ~${Math.round((o as { predicted: number }).predicted)} predicted, no nearby hotspot`;
    else if (id === "alert-core") html = `${(o as AlertFeature).severity.toUpperCase()} · ${(o as AlertFeature).title}`;
    else if (id === "bnd-districts") html = `${(o as { properties?: { district?: string } }).properties?.district ?? "District"}`;
    else if (id === "bnd-taluks") {
      const p = (o as { properties?: { taluk?: string; district?: string } }).properties;
      html = `${p?.taluk ?? "Taluk"}${p?.district ? ` · ${p.district}` : ""}`;
    } else if (id === "bnd-sho") {
      const p = (o as { properties?: { name?: string; district?: string; case_count?: number } }).properties;
      html = `${p?.name ?? "Station"}${p?.district ? ` · ${p.district}` : ""}${p?.case_count != null ? ` · ${p.case_count} cases` : ""}`;
    }
    if (!html) return null;
    return {
      html: escapeHtml(html),
      style: {
        background: "#1d2740",
        color: "#e8ecf6",
        fontSize: "12px",
        padding: "4px 8px",
        borderRadius: "8px",
        border: "1px solid #28324d",
      },
    };
  };

  return (
    <div
      className={cn(
        isFullscreen && "fixed inset-0 z-[80] flex min-h-0 flex-col overflow-hidden bg-bg p-3",
      )}
    >
      {!isFullscreen && <PrintHeader title="Map & Hotspots" />}
      {/* Mode sub-nav */}
      <div className={cn("mb-3 flex flex-wrap items-center justify-between gap-2", isFullscreen && "shrink-0")}>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Map analysis mode">
          {allowedModes.map((m) => {
            const Icon = m.icon;
            const active = mode === m.key;
            return (
              <button
                key={m.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setMode(m.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-13 font-medium transition-colors",
                  active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
                )}
              >
                <Icon className="size-4" />
                {m.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          {aggregateOnly && <Badge variant="neutral">District-aggregate only</Badge>}
          <button
            type="button"
            onClick={() => setIsFullscreen((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface px-2.5 py-1.5 text-13 font-medium text-content transition-colors hover:bg-surface-2"
            aria-label={isFullscreen ? "Exit full screen map" : "Open full screen map"}
            title={isFullscreen ? "Exit full screen (Esc)" : "Open full screen"}
          >
            {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
            <span className="hidden sm:inline">{isFullscreen ? "Restore" : "Full screen"}</span>
          </button>
          <ExportViewButton />
        </div>
      </div>

      {/* Map + floating panels */}
      <div
        className={cn(
          "relative overflow-hidden rounded-card border border-hairline",
          isFullscreen ? "min-h-0 flex-1" : "h-[calc(100vh-11rem)]",
        )}
      >
        <MapCanvas
          viewState={viewState}
          onViewStateChange={setViewState}
          layers={layers}
          getTooltip={getTooltip}
          suppressTooltip={selected != null}
          mapStyle={mapStyle}
          onMapClick={(ll) => {
            if (streetView && !(selected?.type === "case" && selected.approximate)) {
              setStreetView({ lon: ll.lng, lat: ll.lat });
            }
          }}
        >
          {showCoverage && MAPILLARY_TILES && (
            <Source id="mly-coverage" type="vector" tiles={[MAPILLARY_TILES]} minzoom={6} maxzoom={14}>
              <MlLayer id="mly-sequence" type="line" source-layer="sequence" paint={{ "line-color": "#12b981", "line-width": 1.2, "line-opacity": 0.55 }} />
              <MlLayer id="mly-image" type="circle" source-layer="image" minzoom={12} paint={{ "circle-radius": 2, "circle-color": "#12b981", "circle-opacity": 0.6 }} />
            </Source>
          )}
          {streetView && (svCamera ?? streetView) && (
            <Marker longitude={(svCamera ?? streetView).lon} latitude={(svCamera ?? streetView).lat} anchor="center">
              <span className="block size-3 rounded-full border-2 border-white bg-primary shadow" />
            </Marker>
          )}
          {selected?.type === "case" && (
            <CasePopup id={selected.id} lon={selected.lon} lat={selected.lat} onClose={() => setSelected(null)} />
          )}
          {selected?.type === "station" && (
            <StationPopup station={selected.station} onClose={() => setSelected(null)} />
          )}
        </MapCanvas>

        {streetView && (
          <StreetViewPanel
            target={streetView}
            onClose={() => {
              setStreetView(null);
              setSvCamera(null);
            }}
            onImageLocated={(lon, lat) => setSvCamera({ lon, lat })}
          />
        )}

        {/* Left control card */}
        <div className="absolute left-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-72 overflow-y-auto rounded-card border border-hairline bg-surface/95 p-3 shadow-pop backdrop-blur">
          {/* Map view: basemap + 3D (always available) */}
          <div className="mb-3 space-y-2 border-b border-hairline pb-3">
            <div className="flex items-center gap-1.5 text-12 font-semibold text-content-dim">
              <Layers className="size-3.5" /> Map view
            </div>
            <NativeSelect
              value={basemap}
              onChange={(v) => setBasemap(v as BasemapId)}
              options={BASEMAP_OPTIONS.map((b) => ({ value: b.id, label: b.label }))}
              placeholder="Match theme"
              aria-label="Basemap"
            />
            <button
              type="button"
              onClick={() => set3D(!is3D)}
              className={cn(
                "flex w-full items-center justify-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors",
                is3D ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
              )}
            >
              <Box className="size-3.5" /> {is3D ? "3D tilt: on" : "3D tilt"}
            </button>
          </div>
          {/* Optional boundary overlays (state / district / taluk / SHO regions) */}
          <div className="mb-3 space-y-2 border-b border-hairline pb-3">
            <div className="flex items-center gap-1.5 text-12 font-semibold text-content-dim">
              <Shapes className="size-3.5" /> Boundaries
            </div>
            <div className="grid grid-cols-2 gap-1">
              {BOUNDARY_TOGGLES.map(({ key, label, swatch, aggregateSafe }) => {
                if (!aggregateSafe && aggregateOnly) return null;
                const active = boundaries.has(key);
                const q = key === "state" ? stateBndQ : key === "districts" ? distBndQ : key === "taluks" ? talukBndQ : shoBndQ;
                const loading = active && q.isFetching && !q.data;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleBoundary(key)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors",
                      active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
                    )}
                  >
                    <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: swatch }} />
                    <span className="truncate">{label}</span>
                    {loading && <span className="ml-auto text-[10px] opacity-70">…</span>}
                  </button>
                );
              })}
            </div>
            {boundaries.has("sho") && (
              <p className="text-[11px] text-content-dim">
                SHO = police-station jurisdictions (Voronoi of stations, clipped to district).
              </p>
            )}
            {/* Persisted boundary freshness — the map + DB share one versioned
                source of truth; link to the reviewed spatial-repair queue. */}
            {bndFreshnessQ.data && (
              <div className="space-y-1 border-t border-hairline pt-2 text-[11px] text-content-dim">
                <p>
                  Persisted geography:{" "}
                  {["state", "district", "taluk"]
                    .filter((lvl) => bndFreshnessQ.data!.boundaries[lvl])
                    .map((lvl) => `${bndFreshnessQ.data!.boundaries[lvl].count} ${lvl}`)
                    .join(" · ")}
                  {bndFreshnessQ.data.boundaries.district?.version != null
                    && ` · v${bndFreshnessQ.data.boundaries.district.version}`}
                </p>
                {!aggregateOnly && (
                  <div className="flex items-center justify-between">
                    <span>
                      {bndFreshnessQ.data.open_jurisdiction_issues > 0
                        ? `${bndFreshnessQ.data.open_jurisdiction_issues} open jurisdiction issue(s)`
                        : "No open jurisdiction issues"}
                    </span>
                    <Link to="/review/jurisdiction" className="inline-flex items-center gap-1 text-primary hover:underline">
                      <Shield className="size-3" /> Review
                    </Link>
                  </div>
                )}
              </div>
            )}
          </div>
          <ModeControls
            mode={mode}
            aggregateOnly={aggregateOnly}
            pointsCount={visiblePoints.length}
            stationCount={stations.length}
            hotspotCount={hotspotsQ.data?.count}
            forecastCount={forecastQ.data?.count}
            crimeGroups={crimeGroups}
            crimeFilter={crimeFilter}
            setCrimeFilter={setCrimeFilter}
            showStations={showStations}
            setShowStations={setShowStations}
            showLinks={showLinks}
            setShowLinks={setShowLinks}
            linkCount={linksQ.data?.count}
            linkActive={linkHub != null}
            hex3D={hex3D}
            setHex3D={(v) => {
              setHex3D(v);
              if (v && !is3D) set3D(true);
            }}
            tod={tod}
            setTod={setTod}
            horizon={horizon}
            setHorizon={setHorizon}
            zoom={viewState.zoom}
            alerts={activeAlerts}
            ack={(id) => setAckIds((s) => new Set(s).add(id))}
            onAlertClick={(a) => push({ kind: "alert", id: a.alert_id, label: a.title, sublabel: a.district_name ?? a.alert_type })}
          />
          <div className="mt-3 space-y-1.5 border-t border-hairline pt-2.5">
            {hasMapillary() ? (
              <>
                <button
                  type="button"
                  disabled={selected?.type === "case" && selected.approximate}
                  title={selected?.type === "case" && selected.approximate
                    ? "Street view is disabled for an approximate locality reference."
                    : undefined}
                  onClick={() => setStreetView((sv) => (sv ? null : { lon: viewState.longitude, lat: viewState.latitude }))}
                  className={cn(
                    "flex w-full items-center justify-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                    streetView ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
                  )}
                >
                  <Camera className="size-3.5" /> {streetView ? "Close street view" : "Street view"}
                </button>
                <label className="flex cursor-pointer items-center gap-2 px-0.5 text-12 text-content-dim">
                  <input type="checkbox" checked={showCoverage} onChange={(e) => setShowCoverage(e.target.checked)} className="size-3.5 accent-[var(--accent)]" />
                  Show Mapillary coverage
                </label>
                {streetView && <p className="text-[11px] text-content-dim">Click the map to move the camera.</p>}
              </>
            ) : (
              <p className="text-[11px] text-content-dim">
                Set <code className="rounded bg-surface-2 px-1">VITE_MAPILLARY_TOKEN</code> for street view.
              </p>
            )}
          </div>
        </div>

        <Legend
          mode={mode}
          aggregateOnly={aggregateOnly}
          crimeGroups={crimeGroups}
          hasApproximateLocations={hasApproximateLocations}
        />
      </div>
    </div>
  );
}

/* ------------------------------ Controls ---------------------------------- */
function ModeControls({
  mode,
  aggregateOnly,
  pointsCount,
  stationCount,
  hotspotCount,
  forecastCount,
  crimeGroups,
  crimeFilter,
  setCrimeFilter,
  showStations,
  setShowStations,
  showLinks,
  setShowLinks,
  linkCount,
  linkActive,
  hex3D,
  setHex3D,
  tod,
  setTod,
  horizon,
  setHorizon,
  zoom,
  alerts,
  ack,
  onAlertClick,
}: {
  mode: Mode;
  aggregateOnly: boolean;
  pointsCount: number;
  stationCount: number;
  hotspotCount?: number;
  forecastCount?: number;
  crimeGroups: string[];
  crimeFilter: string;
  setCrimeFilter: (v: string) => void;
  showStations: boolean;
  setShowStations: (v: boolean) => void;
  showLinks: boolean;
  setShowLinks: (v: boolean) => void;
  linkCount?: number;
  linkActive: boolean;
  hex3D: boolean;
  setHex3D: (v: boolean) => void;
  tod: string;
  setTod: (v: string) => void;
  horizon: number;
  setHorizon: (v: number) => void;
  zoom: number;
  alerts: AlertFeature[];
  ack: (id: number) => void;
  onAlertClick: (a: AlertFeature) => void;
}) {
  if (aggregateOnly || mode === "forecast" || mode === "patrol") {
    return (
      <div className="space-y-2.5">
        <div className="text-13 font-semibold text-content">{aggregateOnly ? "District forecast" : mode === "patrol" ? "Patrol planning" : "Forecast"}</div>
        <div>
          <div className="mb-1 text-12 text-content-dim">Horizon</div>
          <div className="flex gap-1">
            {HORIZONS.map((h) => (
              <button key={h} type="button" onClick={() => setHorizon(h)} className={cn("flex-1 rounded-control px-2 py-1 text-12 font-medium transition-colors", horizon === h ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content")}>
                {h}d
              </button>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-content-dim">Linear projection from the fused daily forecast.</p>
        </div>
        {forecastCount != null && <div className="tnum text-12 text-content-dim">{formatNumber(forecastCount)} forecast cells</div>}
        {mode === "patrol" && <p className="text-12 text-content-dim">Red rings mark high-forecast cells with no historical hotspot nearby — emerging coverage gaps.</p>}
      </div>
    );
  }

  if (mode === "live") {
    return (
      <div className="space-y-2.5">
        <div className="text-13 font-semibold text-content">Live incidents</div>
        <div>
          <div className="mb-1 text-12 text-content-dim">Crime type</div>
          <NativeSelect
            value={crimeFilter}
            onChange={setCrimeFilter}
            options={crimeGroups.map((g) => ({ value: g, label: g }))}
            placeholder="All crime types"
            aria-label="Crime type filter"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-12 text-content">
          <input type="checkbox" checked={showStations} onChange={(e) => setShowStations(e.target.checked)} className="size-3.5 accent-[var(--primary)]" />
          <Building2 className="size-3.5 text-content-dim" /> Police stations{" "}
          <span className="tnum text-content-dim">({formatNumber(stationCount)})</span>
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-12 text-content">
          <input type="checkbox" checked={showLinks} onChange={(e) => setShowLinks(e.target.checked)} className="size-3.5 accent-[var(--primary)]" />
          <Share2 className="size-3.5 text-content-dim" /> Connected cases (3D arcs)
        </label>
        {showLinks && (
          <p className="rounded-control bg-surface-2/60 px-2 py-1.5 text-[11px] text-content-dim">
            {linkActive
              ? `${linkCount ?? 0} cases linked by shared accused — click a pink node to re-centre.`
              : "Click any incident to arc out to cases sharing an accused."}
          </p>
        )}
        <div className="tnum text-12 text-content-dim">{formatNumber(pointsCount)} incidents shown</div>
        <p className="text-[11px] text-content-dim">
          {zoom < 8.5
            ? "Zoom in to resolve clusters into individual incidents."
            : "Click an incident or station for details."}
          {zoom < STATION_MIN_ZOOM && showStations ? " Stations appear as you zoom in." : ""}
        </p>
      </div>
    );
  }

  if (mode === "hotspots") {
    return (
      <div className="space-y-2">
        <div className="text-13 font-semibold text-content">Density{hex3D ? " (3D hex-bins)" : " (KDE)"}</div>
        <button
          type="button"
          onClick={() => setHex3D(!hex3D)}
          className={cn(
            "flex w-full items-center justify-center gap-1.5 rounded-control px-2 py-1.5 text-12 font-medium transition-colors",
            hex3D ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
          )}
        >
          <Box className="size-3.5" /> {hex3D ? "3D hex-bins: on" : "3D hex-bins"}
        </button>
        <div className="text-12 text-content-dim">Time of day</div>
        <div className="grid grid-cols-1 gap-1">
          {TOD_BUCKETS.map((b) => (
            <button key={b.key} type="button" onClick={() => setTod(b.key)} className={cn("rounded-control px-2 py-1 text-left text-12 font-medium transition-colors", tod === b.key ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content")}>
              {b.label}
            </button>
          ))}
        </div>
        {hotspotCount != null && <div className="tnum text-12 text-content-dim">{hotspotCount} DBSCAN clusters outlined</div>}
      </div>
    );
  }

  // alerts
  return (
    <div className="space-y-2">
      <div className="text-13 font-semibold text-content">Red-zone alerts ({alerts.length})</div>
      <div className="max-h-[46vh] space-y-1 overflow-y-auto">
        {alerts.length === 0 && <p className="text-12 text-content-dim">No active alerts.</p>}
        {alerts.map((a) => (
          <div key={a.alert_id} className="rounded-control border border-hairline p-2">
            <button type="button" onClick={() => onAlertClick(a)} className="block w-full text-left">
              <div className="flex items-center gap-1.5">
                <Badge variant={a.severity === "critical" ? "critical" : a.severity === "high" ? "high" : "medium"} className="capitalize">{a.severity}</Badge>
                <span className="truncate text-12 font-medium text-content">{a.title}</span>
              </div>
              {a.district_name && <div className="mt-0.5 truncate text-[11px] text-content-dim">{a.district_name}</div>}
            </button>
            <button type="button" onClick={() => ack(a.alert_id)} className="mt-1 text-[11px] text-content-dim hover:text-content">
              Acknowledge (session)
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------- Legend ----------------------------------- */
function Legend({
  mode,
  aggregateOnly,
  crimeGroups,
  hasApproximateLocations,
}: {
  mode: Mode;
  aggregateOnly: boolean;
  crimeGroups: string[];
  hasApproximateLocations: boolean;
}) {
  if (!aggregateOnly && mode === "live") {
    const groups = crimeGroups.slice(0, 6);
    if (groups.length === 0 && !hasApproximateLocations) return null;
    return (
      <LegendBox title="Crime type">
        {groups.map((g) => (
          <span key={g} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: categoryColor(g) }} />
            {g}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-primary bg-[#e8ecf6]" />
          Police station
        </span>
        {hasApproximateLocations && (
          <span className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-full border-2 border-content-dim bg-content-dim/10" />
            Locality ring = approximate reference, not exact incident scene
          </span>
        )}
      </LegendBox>
    );
  }
  if (mode === "hotspots") {
    return (
      <LegendBox title="Density (low → high)">
        <Ramp colors={["#0c4a6e", "#0e7490", "#14b8a6", "#84cc16", "#f59e0b", "#dc2626"]} />
        <span className="text-[11px] text-content-dim">scaled to 88th percentile</span>
      </LegendBox>
    );
  }
  if (mode === "forecast" || aggregateOnly || mode === "patrol") {
    return (
      <LegendBox title="Predicted (low → high)">
        <Ramp colors={["#12376b", "#2f7fd1", "#5aa2e8", "#9cc7f5"]} />
        <span className="text-[11px] text-content-dim">Fainter = lower confidence</span>
      </LegendBox>
    );
  }
  return (
    <LegendBox title="Alert severity">
      {["critical", "high", "medium", "low"].map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5 capitalize">
          <span className="size-2.5 rounded-full" style={{ background: `var(--sev-${s})` }} />
          {s}
        </span>
      ))}
    </LegendBox>
  );
}

function LegendBox({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="absolute bottom-3 left-[19rem] z-10 flex max-w-[calc(100%-20rem)] flex-wrap items-center gap-x-3 gap-y-1 rounded-control border border-hairline bg-surface/95 px-2.5 py-1.5 text-12 text-content-dim shadow-sm backdrop-blur">
      <span className="font-medium text-content">{title}:</span>
      {children}
    </div>
  );
}

function Ramp({ colors }: { colors: string[] }) {
  return (
    <span className="inline-flex h-2.5 w-24 overflow-hidden rounded-full">
      {colors.map((c) => (
        <span key={c} className="flex-1" style={{ background: c }} />
      ))}
    </span>
  );
}
