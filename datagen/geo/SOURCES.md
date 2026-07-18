# Karnataka administrative boundaries — sources & build

The generator constrains every synthetic coordinate to the real Karnataka
landmass (state → district → taluk → derived SHO region) using the vendored
GeoJSON in this folder. This removes the "incidents in the Arabian Sea / across
the state border" artefact that came from unbounded Gaussian jitter.

## Vendored files (committed)

| File | Features | Notes |
| --- | --- | --- |
| `karnataka_state.geojson` | 1 | State outline, dissolved from the district polygons. |
| `karnataka_districts.geojson` | 32 | 31 revenue districts + BBMP (Bengaluru city corporation). |
| `karnataka_taluks.geojson` | 230 | Taluks (sub-districts), tagged with their parent district. |

Property schema (normalised to the generator's police-district vocabulary):

- district feature: `{ district, kgis_name, region_id, level:"district" }`
- taluk feature: `{ taluk, district, region_id, level:"taluk" }`
- state feature: `{ name:"Karnataka", level:"state", state_code:29 }`

Geometries are repaired (`buffer(0)`), simplified (~100–135 m tolerance) and
rounded to 5 decimal places, keeping the coastline and state border faithful
while staying small (~1.4 MB total).

## Upstream source & licence

Boundaries originate from **KGIS — Karnataka Geographic Information System**
(Karnataka State Remote Sensing Applications Centre) and the **LGD (Local
Government Directory)** hierarchy, packaged by the open
[One-Health-ARTPARK/geography-data](https://github.com/One-Health-ARTPARK/geography-data)
repository.

- KGIS maps: https://kgis.ksrsac.in/kgis/downloads.aspx
- LGD directory: https://lgdirectory.gov.in/
- Licence: **Government Open Data License – India (GODL-India)** — permits use,
  adaptation and redistribution with attribution. This notice is the attribution.

Content was adapted (filtered to Karnataka, renamed to the generator's district
vocabulary, repaired and simplified) for compliance and fitness of purpose.

## Reproducing the vendored files

```bash
# 1. fetch the full-resolution source into datagen/geo/raw/ (gitignored, ~44 MB)
#    districts (all 31 + BBMP, 15 MB):
curl -sL -o datagen/geo/raw/state_29_districts.geojson \
  https://raw.githubusercontent.com/One-Health-ARTPARK/geography-data/HEAD/output/maps/subregions/state_29.geojson
#    taluks per district (LGD codes 524-550, 630, 631, 635, 738):
for c in $(seq 524 550) 630 631 635 738; do \
  curl -sL -o datagen/geo/raw/taluks_district_$c.geojson \
    https://raw.githubusercontent.com/One-Health-ARTPARK/geography-data/HEAD/output/maps/subregions/district_$c.geojson; done

# 2. build the simplified, vendored files
python datagen/geo/build_boundaries.py
```
