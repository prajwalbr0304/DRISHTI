"""Offline self-test for datagen.boundaries (no database, no data generation).

Verifies the real Karnataka boundaries load, the containment hierarchy works,
uniform / clustered sampling stays in-state, and Voronoi SHO regions tile a
district. Run:  python -m datagen.geo.selftest   (from repo root)
"""
from __future__ import annotations

import sys

import numpy as np

from datagen import boundaries as B
from datagen.reference import KARNATAKA_DISTRICTS


def main() -> int:
    gen = np.random.default_rng(7)
    b = B.load_boundaries()
    fails = []

    # 1. inventory
    n_dist = len(b.district_names)
    n_taluk = sum(len(b.taluks(d)) for d in b.district_names if b._taluks.get(d))
    print(f"districts loaded : {n_dist}")
    print(f"taluks loaded    : {n_taluk}")
    if n_dist < 31:
        fails.append(f"expected >=31 districts, got {n_dist}")

    # 2. every reference district resolves to a polygon
    missing = [name for (name, *_1) in KARNATAKA_DISTRICTS if b.district(name) is None]
    if missing:
        fails.append(f"reference districts with no polygon: {missing}")
    print(f"reference districts mapped: {len(KARNATAKA_DISTRICTS) - len(missing)}/{len(KARNATAKA_DISTRICTS)}")

    # 3. reference centroids fall inside the state
    outside = [name for (name, lat, lon, *_2) in KARNATAKA_DISTRICTS if not b.in_state(lon, lat)]
    if outside:
        # some official centroids sit just off the simplified border; report only
        print(f"NOTE centroids just outside simplified state outline: {outside}")

    # 4. known-point containment
    checks = [
        ("Bengaluru", 77.5946, 12.9716, True),
        ("Mangaluru", 74.8560, 12.8700, True),
        ("Mysuru", 76.6394, 12.2958, True),
        ("Arabian Sea (off Karwar)", 74.00, 14.80, False),
        ("Chennai (Tamil Nadu)", 80.2707, 13.0827, False),
        ("Hyderabad (Telangana)", 78.4867, 17.3850, False),
    ]
    for label, lon, lat, expected in checks:
        got = b.in_state(lon, lat)
        ok = got == expected
        print(f"  in_state {label:26s} -> {got!s:5s} (want {expected}) {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"in_state({label}) = {got}, expected {expected}")

    # 5. district_of / taluk_of for a coastal city
    dn = b.district_of(74.8560, 12.8700)
    tn = b.taluk_of(74.8560, 12.8700, dn)
    print(f"  Mangaluru resolves to district={dn!r} taluk={tn!r}")
    if dn != "Dakshina Kannada":
        fails.append(f"Mangaluru district_of={dn!r}, expected 'Dakshina Kannada'")

    # 6. uniform sampling stays inside the district (the real placement boundary)
    #    and therefore on real Karnataka land; in-state is reported too.
    import shapely
    for dname in ("Uttara Kannada", "Dakshina Kannada", "Bengaluru Urban", "Kalaburagi"):
        region = b.district(dname)
        pts = B.uniform_points(region.geom, region.bounds, gen, 500)
        in_dist = int(np.count_nonzero(shapely.contains_xy(region.geom, pts[:, 0], pts[:, 1])))
        in_state = int(np.count_nonzero([b.in_state(x, y) for x, y in pts]))
        print(f"  uniform 500 in {dname:18s}: in-district={in_dist}/500  in-state={in_state}/500")
        if in_dist < 500:
            fails.append(f"{dname}: {500 - in_dist} sampled points left the district")
        if in_state < 500:
            fails.append(f"{dname}: {500 - in_state} points left the state outline")

    # 7. SHO Voronoi regions tile a district
    region = b.district("Tumakuru")
    seeds = B.uniform_points(region.geom, region.bounds, gen, 12)
    cells = B.sho_regions(seeds, region.geom)
    covered = sum(c.area for c in cells)
    ratio = covered / region.area
    print(f"  SHO cells for Tumakuru: {len(cells)} cells cover {ratio:.3f} of district area")
    if not (0.97 <= ratio <= 1.03):
        fails.append(f"SHO cells cover {ratio:.3f} of Tumakuru (expected ~1.0)")

    # 8. clustered sample_near stays inside its cell
    cell_region = B.Region("cell0", cells[0], level="sho")
    cx, cy = seeds[0]
    bad = 0
    for _ in range(300):
        x, y = B.sample_near(cell_region, cx, cy, 0.02, gen)
        if not cell_region.contains(x, y):
            bad += 1
    print(f"  sample_near escapes cell: {bad}/300")
    if bad > 0:
        fails.append(f"sample_near left the SHO cell {bad} times")

    # 9. end-to-end placement simulation — mirrors lookups.plan_stations +
    #    cases.Planner._incident_point exactly, but with no database.
    sim_total = 0
    sim_out = 0
    stn_out = 0
    for dname in ("Uttara Kannada", "Dakshina Kannada", "Udupi", "Belagavi", "Bengaluru City"):
        region = b.district(dname)
        taluks = b.taluks(dname)
        plans = B.plan_stations(region, taluks, 30, gen)
        for lon, lat, tname, ring in plans:
            if not region.contains(lon, lat):
                stn_out += 1
            cell = B.region_from_ring("sho", ring) if len(ring) >= 4 else region
            sigma = B.sigma_for_area(cell.area)
            for _ in range(20):  # 20 incidents per station
                ilon, ilat = B.sample_near(cell, lon, lat, sigma, gen)
                sim_total += 1
                if not b.in_state(ilon, ilat):
                    sim_out += 1
    print(f"  placement sim: stations={30 * 5} out-of-district={stn_out}; "
          f"incidents={sim_total} out-of-state={sim_out}")
    if stn_out:
        fails.append(f"{stn_out} simulated stations fell outside their district")
    if sim_out:
        fails.append(f"{sim_out}/{sim_total} simulated incidents fell outside Karnataka")

    print()
    if fails:
        print("SELF-TEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELF-TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
