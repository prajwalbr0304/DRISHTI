"""Shared, read-only generation context passed to worker processes.

Everything here is plain data (ints/lists/dicts/tuples) so it pickles cheaply
for multiprocessing ``spawn`` on Windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Context:
    state_id: int = 1

    # districts[i] = {id,name,lat,lon,tags,pop_weight}
    districts: List[dict] = field(default_factory=list)
    district_weights: List[float] = field(default_factory=list)

    # stations[i] = {id, district_idx, lat, lon, radius}
    stations: List[dict] = field(default_factory=list)
    stations_by_district: Dict[int, List[int]] = field(default_factory=dict)  # dist_idx -> station indices
    officers_by_station: Dict[int, List[int]] = field(default_factory=dict)    # station_id -> officer ids
    courts_by_district: Dict[int, List[int]] = field(default_factory=dict)     # dist_idx -> court ids
    district_hq_unit: Dict[int, int] = field(default_factory=dict)             # dist_idx -> HQ unit id

    # resolved crime profiles (profile dict + resolved ids)
    crime_profiles: List[dict] = field(default_factory=list)
    crime_weights: List[float] = field(default_factory=list)

    # lookup id maps
    gravity_id: Dict[str, int] = field(default_factory=dict)
    category_id: Dict[str, int] = field(default_factory=dict)
    category_code: Dict[str, int] = field(default_factory=dict)
    status_ids: List[int] = field(default_factory=list)
    religion_ids: List[int] = field(default_factory=list)
    religion_weights: List[float] = field(default_factory=list)
    caste_ids: List[int] = field(default_factory=list)
    occupation_ids: List[int] = field(default_factory=list)

    # criminal population
    offenders: List[dict] = field(default_factory=list)  # {name,gender,home_dist,age_base,specialty,is_juvenile}
    gangs: List[dict] = field(default_factory=list)       # {name,home_dist,specialty,members:[offender_idx],vehicles:[...]}

    # bookkeeping
    n_firs: int = 0
