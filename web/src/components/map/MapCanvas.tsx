import type { ReactNode } from "react";
import type { StyleSpecification } from "maplibre-gl";
import Map, { NavigationControl, useControl } from "react-map-gl/maplibre";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer, PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { useUIStore } from "@/stores/useUIStore";
import { MAP_STYLES } from "@/components/map/mapConfig";

/* ============================================================================
   Full-bleed MapLibre base map with a deck.gl overlay (doc 05 §5 rendering
   stack). The basemap follows the Ops/Desk theme; all data is drawn by deck.gl
   layers supplied by the parent.
   ========================================================================== */

export interface MapViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

type TooltipGetter = (info: PickingInfo) => string | { html: string } | null;

function DeckOverlay({ layers, getTooltip }: { layers: Layer[]; getTooltip?: TooltipGetter }) {
  const overlay = useControl(
    () => new MapboxOverlay({ interleaved: false, layers }),
  ) as MapboxOverlay;
  overlay.setProps({ layers, getTooltip });
  return null;
}

export function MapCanvas({
  viewState,
  onViewStateChange,
  layers,
  getTooltip,
  onMapClick,
  mapStyle,
  children,
}: {
  viewState: MapViewState;
  onViewStateChange: (v: MapViewState) => void;
  layers: Layer[];
  getTooltip?: TooltipGetter;
  onMapClick?: (lngLat: { lng: number; lat: number }) => void;
  mapStyle?: string | StyleSpecification;
  children?: ReactNode;
}) {
  const theme = useUIStore((s) => s.theme);
  const style = mapStyle ?? (theme === "ops" ? MAP_STYLES.ops : MAP_STYLES.desk);

  return (
    <Map
      reuseMaps
      longitude={viewState.longitude}
      latitude={viewState.latitude}
      zoom={viewState.zoom}
      pitch={viewState.pitch}
      bearing={viewState.bearing}
      maxPitch={75}
      onMove={(e) => onViewStateChange(e.viewState as MapViewState)}
      onClick={(e) => onMapClick?.(e.lngLat)}
      mapStyle={style}
      attributionControl={false}
      style={{ position: "absolute", inset: 0 }}
    >
      <NavigationControl position="top-right" visualizePitch showCompass />
      <DeckOverlay layers={layers} getTooltip={getTooltip} />
      {children}
    </Map>
  );
}
