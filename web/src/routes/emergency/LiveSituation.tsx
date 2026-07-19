import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Layer } from "@deck.gl/core";
import { api } from "@/api";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import { cn } from "@/lib/utils";
import { districtName } from "@/stores/useDisasterStore";
import { DistrictPicker, SyntheticNote, useErCapabilities } from "@/routes/emergency/erShared";
import {
  ER_LEGEND, hazardExtentLayer, resourceLayer, riskZoneLayer, routeLayer,
  sensorLayer, shelterLayer,
} from "@/routes/emergency/erLayers";

const KARNATAKA: MapViewState = {
  longitude: 75.9, latitude: 14.8, zoom: 6.1, pitch: 0, bearing: 0,
};

type LayerKey = "hazards" | "zones" | "sensors" | "resources" | "shelters" | "routes";

export function LiveSituation() {
  const { activeDistrict } = useErCapabilities();
  const [view, setView] = useState<MapViewState>(KARNATAKA);
  const [on, setOn] = useState<Record<LayerKey, boolean>>({
    hazards: true, zones: true, sensors: true, resources: true, shelters: true, routes: true,
  });

  const d = activeDistrict ?? undefined;
  const events = useQuery({ queryKey: ["er", "events", d], queryFn: ({ signal }) => api.disaster.events({ district_id: d }, signal) });
  const zones = useQuery({ queryKey: ["er", "zones", d], queryFn: ({ signal }) => api.disaster.zones({ district_id: d }, signal) });
  const readings = useQuery({ queryKey: ["er", "readings", d], queryFn: ({ signal }) => api.disaster.readings({ district_id: d }, signal) });
  const resources = useQuery({ queryKey: ["er", "resources", d], queryFn: ({ signal }) => api.disaster.resources({ district_id: d }, signal) });
  const shelters = useQuery({ queryKey: ["er", "shelters", d], queryFn: ({ signal }) => api.disaster.shelters({ district_id: d }, signal) });
  const routes = useQuery({ queryKey: ["er", "routes"], queryFn: ({ signal }) => api.disaster.routes({}, signal) });

  const layers = useMemo<Layer[]>(() => {
    const out: Layer[] = [];
    if (on.zones && zones.data) out.push(riskZoneLayer(zones.data.zones));
    if (on.hazards && events.data) out.push(hazardExtentLayer(events.data.events));
    if (on.routes && routes.data) out.push(routeLayer(routes.data.routes));
    if (on.sensors && readings.data) out.push(sensorLayer(readings.data.readings));
    if (on.resources && resources.data) out.push(resourceLayer(resources.data.resources));
    if (on.shelters && shelters.data) out.push(shelterLayer(shelters.data.shelters));
    return out;
  }, [on, events.data, zones.data, readings.data, resources.data, shelters.data, routes.data]);

  const toggles: { key: LayerKey; label: string }[] = [
    { key: "hazards", label: "Hazards" }, { key: "zones", label: "Risk zones" },
    { key: "sensors", label: "Sensors" }, { key: "resources", label: "Resources" },
    { key: "shelters", label: "Shelters" }, { key: "routes", label: "Routes" },
  ];

  return (
    <div className="space-y-3">
      <PageHeader
        title="Live Situation"
        description={`Hazard extents, risk zones, sensors, resources and routes — ${districtName(activeDistrict)}`}
        actions={<DistrictPicker />}
      />

      <div className="flex flex-wrap items-center gap-2">
        {toggles.map((t) => (
          <button key={t.key} type="button"
            onClick={() => setOn((s) => ({ ...s, [t.key]: !s[t.key] }))}
            className={cn("rounded-full border px-2.5 py-1 text-12 transition-colors",
              on[t.key] ? "border-primary/40 bg-primary/10 text-content" : "border-hairline text-content-dim")}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="relative h-[62vh] overflow-hidden rounded-control border border-hairline">
        <MapCanvas
          viewState={view}
          onViewStateChange={setView}
          layers={layers}
          getTooltip={(info) => {
            const o = info.object as Record<string, unknown> | undefined;
            if (!o) return null;
            const p = (o.properties as Record<string, unknown>) ?? o;
            const bits = Object.entries(p)
              .filter(([, v]) => typeof v === "string" || typeof v === "number")
              .slice(0, 5)
              .map(([k, v]) => `${k}: ${v}`);
            return bits.length ? bits.join("\n") : null;
          }}
        />
        {/* legend */}
        <div className="absolute bottom-3 left-3 rounded-control border border-hairline bg-surface/90 px-3 py-2 backdrop-blur">
          <div className="mb-1 text-11 font-semibold text-content">Legend</div>
          <ul className="space-y-0.5">
            {ER_LEGEND.map((l) => (
              <li key={l.label} className="flex items-center gap-2 text-11 text-content-dim">
                <span className="inline-block size-2.5 rounded-full" style={{ backgroundColor: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>
        </div>
        {/* observed/predicted/synthetic note */}
        <div className="absolute right-3 top-3">
          <Badge variant="neutral">Observed · Predicted · Synthetic</Badge>
        </div>
      </div>

      <SyntheticNote />
    </div>
  );
}
