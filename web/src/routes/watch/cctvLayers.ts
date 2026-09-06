import { ArcLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type {
  CctvAlert, CctvCamera, CctvDispatch, CctvResponder,
} from "@/api/endpoints/cctv";

/* ============================================================================
   deck.gl layers for the CCTV watch wall.

   Palette logic, so the map is readable at a glance without a legend lookup:
     * cameras are NEUTRAL by default — a camera is infrastructure, not an alarm.
       It only takes a severity colour when it currently has an open alert.
     * an offline / maintenance camera is drawn hollow and dim, because a dark
       camera silently reading as "monitored" is the most dangerous thing this
       map could imply.
     * responders are teal/green (readiness), matching the Emergency Response
       resource palette rather than the incident palette.
     * only PENDING and CONFIRMED alerts pulse. A resolved or dismissed alert
       stops moving, so motion on this map always means "needs attention".
   ========================================================================== */

type RGBA = [number, number, number, number];

const SEVERITY_RGBA: Record<string, RGBA> = {
  minor: [250, 204, 21, 235],
  moderate: [249, 115, 22, 240],
  severe: [239, 68, 68, 245],
  extreme: [190, 18, 60, 255],
};

const SEVERITY_HEX: Record<string, string> = {
  minor: "#facc15", moderate: "#f97316", severe: "#ef4444", extreme: "#be123c",
};

/** Camera body colour by health. Neutral when nothing is wrong. */
const CAMERA_RGBA: Record<string, RGBA> = {
  online: [148, 197, 253, 235],
  degraded: [251, 191, 36, 235],
  offline: [100, 116, 139, 120],
  maintenance: [148, 163, 184, 130],
};

const RESPONDER_RGBA: Record<string, RGBA> = {
  available: [16, 185, 129, 240],
  engaged: [79, 70, 229, 240],
  offline: [100, 116, 139, 120],
};

export function severityHex(severity?: string | null): string {
  return SEVERITY_HEX[(severity || "moderate").toLowerCase()] ?? SEVERITY_HEX.moderate;
}

function cameraFill(c: CctvCamera): RGBA {
  // An open alert overrides health colour: the incident is what matters now.
  if (c.open_alert_count > 0 && c.top_open_severity) {
    return SEVERITY_RGBA[c.top_open_severity.toLowerCase()] ?? SEVERITY_RGBA.moderate;
  }
  return CAMERA_RGBA[c.status] ?? CAMERA_RGBA.online;
}

/** Cameras as pickable points. Radius grows with the open-alert count. */
export function cameraMarkers(
  cameras: CctvCamera[],
  onClick?: (c: CctvCamera) => void,
  selectedId?: number | null,
): Layer {
  return new ScatterplotLayer<CctvCamera>({
    id: "cctv-cameras",
    data: cameras,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: (d) => cameraFill(d),
    // A dark camera is drawn hollow so it cannot be mistaken for a watched one.
    filled: true,
    stroked: true,
    getLineColor: (d) =>
      d.camera_id === selectedId
        ? [255, 255, 255, 255]
        : d.status === "offline" || d.status === "maintenance"
          ? [148, 163, 184, 200]
          : [15, 23, 42, 220],
    lineWidthUnits: "pixels",
    getLineWidth: (d) => (d.camera_id === selectedId ? 2.5 : 1.2),
    getRadius: (d) => (d.open_alert_count > 0 ? 9 : 6),
    radiusUnits: "pixels",
    radiusMinPixels: 5,
    radiusMaxPixels: 14,
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as CctvCamera) : undefined,
    updateTriggers: {
      getFillColor: [cameras.map((c) => `${c.open_alert_count}:${c.top_open_severity}`).join(",")],
      getLineColor: [selectedId],
      getLineWidth: [selectedId],
      getRadius: [cameras.map((c) => c.open_alert_count).join(",")],
    },
  });
}

/** Field-of-view wedges, so coverage direction is visible rather than implied. */
export function cameraViewCones(cameras: CctvCamera[]): Layer {
  const wedges = cameras
    .filter((c) => c.bearing_degrees != null && c.status !== "offline"
      && c.status !== "maintenance")
    .map((c) => {
      const bearing = c.bearing_degrees as number;
      const fov = c.fov_degrees ?? 70;
      // ~180 m of visible throw, expressed in degrees. Latitude is compressed by
      // cos(lat) so the wedge keeps its shape away from the equator.
      const reach = 0.0016;
      const latScale = Math.cos((c.lat * Math.PI) / 180) || 1;
      const pts: [number, number][] = [[c.lon, c.lat]];
      const steps = 10;
      for (let i = 0; i <= steps; i++) {
        const a = bearing - fov / 2 + (fov * i) / steps;
        const rad = (a * Math.PI) / 180;
        pts.push([
          c.lon + (Math.sin(rad) * reach) / latScale,
          c.lat + Math.cos(rad) * reach,
        ]);
      }
      pts.push([c.lon, c.lat]);
      return { polygon: pts, camera: c };
    });
  return new PolygonLayer<{ polygon: [number, number][]; camera: CctvCamera }>({
    id: "cctv-view-cones",
    data: wedges,
    getPolygon: (d) => d.polygon,
    filled: true,
    stroked: false,
    getFillColor: (d) =>
      d.camera.open_alert_count > 0
        ? [239, 68, 68, 46]
        : [148, 197, 253, 26],
    pickable: false,
    updateTriggers: {
      getFillColor: [wedges.map((w) => w.camera.open_alert_count).join(",")],
    },
  });
}

/** Expanding ring under an alert. `pulse` is a 0..1 phase driven by the page. */
export function alertPulse(alerts: CctvAlert[], pulse: number): Layer {
  const live = alerts.filter((a) => a.lon != null && a.lat != null);
  return new ScatterplotLayer<CctvAlert>({
    id: "cctv-alert-pulse",
    data: live,
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) => {
      const base = SEVERITY_RGBA[(d.severity || "moderate").toLowerCase()]
        ?? SEVERITY_RGBA.moderate;
      // Fade out as the ring expands so it reads as a pulse, not a blob.
      return [base[0], base[1], base[2], Math.round(150 * (1 - pulse))];
    },
    getRadius: 14 + pulse * 26,
    radiusUnits: "pixels",
    radiusMinPixels: 10,
    radiusMaxPixels: 52,
    stroked: false,
    pickable: false,
    updateTriggers: { getFillColor: [pulse], getRadius: [pulse] },
  });
}

/** The solid, clickable alert marker. */
export function alertCore(alerts: CctvAlert[], onClick?: (a: CctvAlert) => void): Layer {
  const live = alerts.filter((a) => a.lon != null && a.lat != null);
  return new ScatterplotLayer<CctvAlert>({
    id: "cctv-alert-core",
    data: live,
    getPosition: (d) => [d.lon as number, d.lat as number],
    getFillColor: (d) =>
      SEVERITY_RGBA[(d.severity || "moderate").toLowerCase()] ?? SEVERITY_RGBA.moderate,
    getRadius: 7,
    radiusUnits: "pixels",
    radiusMinPixels: 6,
    radiusMaxPixels: 13,
    stroked: true,
    // A confirmed alert gets a white ring — a human has vouched for it, and that
    // distinction should be visible on the map, not only in the queue.
    getLineColor: (d) =>
      d.status === "proposed" ? [15, 23, 42, 220] : [255, 255, 255, 245],
    lineWidthUnits: "pixels",
    getLineWidth: (d) => (d.status === "proposed" ? 1.2 : 2),
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as CctvAlert) : undefined,
    updateTriggers: {
      getLineColor: [alerts.map((a) => a.status).join(",")],
      getLineWidth: [alerts.map((a) => a.status).join(",")],
    },
  });
}

/** Responders (stations, patrol cars, traffic bikes). */
export function responderMarkers(
  responders: CctvResponder[],
  onClick?: (r: CctvResponder) => void,
): Layer {
  return new ScatterplotLayer<CctvResponder>({
    id: "cctv-responders",
    data: responders,
    getPosition: (d) => [d.lon, d.lat],
    getFillColor: (d) => RESPONDER_RGBA[d.status] ?? RESPONDER_RGBA.available,
    // A station is a fixed point and drawn larger than a mobile unit.
    getRadius: (d) => (d.kind === "station" ? 7 : 5),
    radiusUnits: "pixels",
    radiusMinPixels: 4,
    radiusMaxPixels: 12,
    stroked: true,
    getLineColor: [255, 255, 255, 190],
    lineWidthUnits: "pixels",
    getLineWidth: 1,
    pickable: true,
    onClick: onClick ? (info) => info.object && onClick(info.object as CctvResponder) : undefined,
    updateTriggers: {
      getFillColor: [responders.map((r) => r.status).join(",")],
    },
  });
}

/** Arc from the assigned responder to the incident, for dispatches in flight. */
export function dispatchArcs(
  dispatches: CctvDispatch[],
  alertById: Map<number, CctvAlert>,
  responderById: Map<number, CctvResponder>,
): Layer {
  const links = dispatches
    .map((d) => {
      const alert = alertById.get(d.cctv_alert_id);
      const responder = d.patrol_unit_id != null
        ? responderById.get(d.patrol_unit_id)
        : undefined;
      if (!alert || alert.lon == null || alert.lat == null || !responder) return null;
      return {
        from: [responder.lon, responder.lat] as [number, number],
        to: [alert.lon, alert.lat] as [number, number],
        status: d.status,
      };
    })
    .filter((x): x is { from: [number, number]; to: [number, number]; status: string } => x != null);
  return new ArcLayer<{ from: [number, number]; to: [number, number]; status: string }>({
    id: "cctv-dispatch-arcs",
    data: links,
    getSourcePosition: (d) => d.from,
    getTargetPosition: (d) => d.to,
    // A proposal is dashed-feeling (dim); an actually-dispatched unit is bright.
    getSourceColor: (d) => (d.status === "proposed" ? [56, 189, 248, 120] : [16, 185, 129, 235]),
    getTargetColor: (d) => (d.status === "proposed" ? [239, 68, 68, 120] : [239, 68, 68, 235]),
    getWidth: (d) => (d.status === "proposed" ? 1.5 : 3),
    widthUnits: "pixels",
    getHeight: 0.25,
    pickable: false,
    updateTriggers: {
      getSourceColor: [links.map((l) => l.status).join(",")],
      getTargetColor: [links.map((l) => l.status).join(",")],
      getWidth: [links.map((l) => l.status).join(",")],
    },
  });
}

export const CCTV_LEGEND: { label: string; color: string }[] = [
  { label: "Camera — monitored", color: "#94c5fd" },
  { label: "Camera — degraded", color: "#fbbf24" },
  { label: "Camera — offline (not watched)", color: "#64748b" },
  { label: "Alert — awaiting review", color: "#f97316" },
  { label: "Alert — confirmed / severe", color: "#ef4444" },
  { label: "Responder — available", color: "#10b981" },
  { label: "Responder — engaged", color: "#4f46e5" },
];
