/* ============================================================================
   Mini jurisdiction density (doc 03 §2.5, compact form). A lightweight spatial
   scatter of REAL hotspot centroids — dot size + opacity encode intensity — for
   an at-a-glance "where's the heat" read on the Command Center. The full
   deck.gl/MapLibre map lives in the Map & Hotspots destination (Phase 15e).
   ========================================================================== */

export interface DensityPoint {
  lon: number;
  lat: number;
  weight: number; // 0..1 intensity
  label?: string;
}

const W = 160;
const H = 100;
const PAD = 8;

export function MiniDensity({ points }: { points: DensityPoint[] }) {
  const pts = points.filter((p) => Number.isFinite(p.lon) && Number.isFinite(p.lat));

  if (pts.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-13 text-content-dim">
        No mapped incidents in this scope.
      </div>
    );
  }

  const lons = pts.map((p) => p.lon);
  const lats = pts.map((p) => p.lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const spanLon = maxLon - minLon || 1;
  const spanLat = maxLat - minLat || 1;

  const project = (lon: number, lat: number) => {
    const x = PAD + ((lon - minLon) / spanLon) * (W - 2 * PAD);
    // invert lat so north is up
    const y = PAD + (1 - (lat - minLat) / spanLat) * (H - 2 * PAD);
    return { x, y };
  };

  return (
    <div>
      <div className="overflow-hidden rounded-control border border-hairline bg-surface-2/40">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Incident density">
          {/* faint grid */}
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={`v${f}`} x1={W * f} y1={0} x2={W * f} y2={H} stroke="var(--border)" strokeWidth={0.3} />
          ))}
          {[0.33, 0.66].map((f) => (
            <line key={`h${f}`} x1={0} y1={H * f} x2={W} y2={H * f} stroke="var(--border)" strokeWidth={0.3} />
          ))}
          {pts.map((p, i) => {
            const { x, y } = project(p.lon, p.lat);
            const w = Math.max(0, Math.min(1, p.weight));
            return (
              <circle
                key={i}
                cx={x}
                cy={y}
                r={1.6 + w * 3.6}
                fill="var(--primary)"
                fillOpacity={0.25 + w * 0.5}
                stroke="var(--primary)"
                strokeWidth={0.4}
              />
            );
          })}
        </svg>
      </div>
      <div className="mt-1.5 flex items-center justify-between text-12 text-content-dim">
        <span className="tnum">{pts.length} hotspots</span>
        <span>dot size · opacity = intensity</span>
      </div>
    </div>
  );
}
