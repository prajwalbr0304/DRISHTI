"""Deterministic synthetic CCTV estate: cameras + dispatchable responders.

Unlike the disaster module (which loads a committed ``datagen`` fixture), the CCTV
estate is small and fully declarative, so it is defined here in code. That keeps it
available in the minimal AppSail image, which copies only ``app/`` and ``sql/``
and therefore has no ``datagen`` tree.

Coordinates are real Karnataka junctions and the station names are real
station-area names, because a demo map with invented geography is impossible to
sanity-check. Everything else — the incidents, the callsigns, the responder
positions — is synthetic, and every row the detector later produces is labelled
as such.

Seeding is idempotent: rows are keyed by ``Code``, so re-running updates position
and metadata in place rather than duplicating the estate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..config import get_settings
from .repo import CctvRepo, cctv_repo


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# (code, name, location label, lon, lat, district_id, unit_id, bearing,
#  status, detector profile)
# detector profile "" == watch for every class.
_CAMERAS: tuple[tuple[str, str, str, float, float, int, Optional[int], float, str, str], ...] = (
    # --- Bengaluru Urban (5) — dense junction coverage -----------------------
    ("BLR-TRC-01", "Trinity Circle Mast 01", "MG Road x Trinity Circle",
     77.6197, 12.9730, 5, None, 95.0, "online", ""),
    ("BLR-MGR-04", "MG Road Lightpost 04", "MG Road near Metro entry",
     77.6100, 12.9752, 5, None, 270.0, "online",
     "fight,road_rage,crowd_surge,abandoned_object"),
    ("BLR-HBL-02", "Hebbal Flyover Gantry 02", "Hebbal Flyover southbound ramp",
     77.5910, 13.0358, 5, None, 180.0, "online",
     "traffic_block,vehicle_accident,road_rage"),
    ("BLR-SLK-07", "Silk Board Gantry 07", "Silk Board Junction",
     77.6228, 12.9172, 5, None, 45.0, "online",
     "traffic_block,vehicle_accident,road_rage"),
    ("BLR-KRM-03", "KR Market Dome 03", "KR Market north entrance",
     77.5766, 12.9633, 5, None, 20.0, "online",
     "crowd_surge,fight,abandoned_object,person_down"),
    ("BLR-MAJ-11", "Majestic Concourse 11", "Kempegowda Bus Station concourse",
     77.5726, 12.9776, 5, None, 130.0, "online",
     "crowd_surge,fight,abandoned_object,trespass"),
    ("BLR-IND-06", "Indiranagar 100ft Mast 06", "100 Feet Road x 12th Main",
     77.6408, 12.9719, 5, None, 300.0, "degraded", ""),
    ("BLR-ELC-09", "Electronic City Toll 09", "Hosur Road toll plaza",
     77.6770, 12.8452, 5, None, 200.0, "online",
     "traffic_block,vehicle_accident"),
    ("BLR-YPR-05", "Yeshwanthpur Circle 05", "Yeshwanthpur Circle",
     77.5540, 13.0234, 5, None, 75.0, "online", ""),
    ("BLR-CBP-08", "Cubbon Park Gate 08", "Cubbon Park Kasturba Road gate",
     77.5946, 12.9763, 5, None, 15.0, "offline",
     "trespass,person_down,fight"),

    # --- Dakshina Kannada (24) — Mangaluru ----------------------------------
    ("MNG-HMP-01", "Hampankatta Mast 01", "Hampankatta Circle",
     74.8420, 12.8703, 24, None, 110.0, "online", ""),
    ("MNG-CLK-02", "Clock Tower Dome 02", "State Bank x Clock Tower",
     74.8380, 12.8650, 24, None, 250.0, "online",
     "fight,crowd_surge,road_rage"),
    ("MNG-PMP-03", "Pumpwell Gantry 03", "Pumpwell Circle flyover",
     74.8590, 12.8580, 24, None, 190.0, "online",
     "traffic_block,vehicle_accident,road_rage"),
    ("MNG-PNB-04", "Panambur Beach Road 04", "Panambur Beach approach road",
     74.8010, 12.9420, 24, None, 340.0, "online",
     "crowd_surge,trespass,person_down"),

    # --- Mysuru (22) --------------------------------------------------------
    ("MYS-PAL-01", "Palace North Gate 01", "Mysuru Palace north gate",
     76.6552, 12.3052, 22, None, 5.0, "online",
     "crowd_surge,abandoned_object,trespass"),
    ("MYS-KRC-02", "KR Circle Mast 02", "K R Circle",
     76.6494, 12.3072, 22, None, 220.0, "online", ""),
    ("MYS-BNM-03", "Bannimantap Ground 03", "Bannimantap parade ground",
     76.6560, 12.3320, 22, None, 160.0, "maintenance", ""),

    # --- Udupi (27) ---------------------------------------------------------
    ("UDP-SBS-01", "Service Bus Stand 01", "Udupi service bus stand",
     74.7500, 13.3400, 27, None, 80.0, "online",
     "crowd_surge,fight,abandoned_object"),
    ("UDP-MLP-02", "Malpe Beach Road 02", "Malpe beach road junction",
     74.7050, 13.3500, 27, None, 300.0, "online", ""),

    # --- Kalaburagi (16) ----------------------------------------------------
    ("KLB-CBS-01", "Central Bus Stand 01", "Kalaburagi central bus stand",
     76.8340, 17.3290, 16, None, 100.0, "online",
     "crowd_surge,fight,traffic_block"),
    ("KLB-SMC-02", "Super Market Circle 02", "Super Market Circle",
     76.8290, 17.3350, 16, None, 210.0, "online", ""),

    # --- Uttara Kannada (28) ------------------------------------------------
    ("KAR-BCH-01", "Karwar Beach Road 01", "Karwar beach road promenade",
     74.1240, 14.8130, 28, None, 265.0, "online",
     "crowd_surge,trespass,person_down"),
)

# (code, name, kind, lon, lat, district_id, unit_id, contact label, capabilities)
# "Hoysala" and "Cheetah" are the real names Karnataka police use for their
# patrol car and patrol bike fleets, which makes the callsigns readable to an
# actual operator. The numbers are synthetic.
_RESPONDERS: tuple[tuple[str, str, str, float, float, int, Optional[int], str, list[str]], ...] = (
    # Bengaluru Urban
    ("PS-CUBBON", "Cubbon Park Police Station", "station",
     77.5952, 12.9739, 5, None, "Control room ref CP-01", ["riot_control", "first_aid"]),
    ("PS-HALASURU", "Halasuru Gate Police Station", "station",
     77.6062, 12.9698, 5, None, "Control room ref HG-01", ["riot_control"]),
    ("PS-ASHOKNAGAR", "Ashok Nagar Police Station", "station",
     77.6055, 12.9673, 5, None, "Control room ref AN-01", ["riot_control", "traffic"]),
    ("PS-HEBBAL", "Hebbal Police Station", "station",
     77.5885, 13.0348, 5, None, "Control room ref HB-01", ["traffic", "first_aid"]),
    ("PS-MADIWALA", "Madiwala Police Station", "station",
     77.6180, 12.9226, 5, None, "Control room ref MD-01", ["traffic"]),
    ("PS-UPPARPET", "Upparpet Police Station", "station",
     77.5748, 12.9761, 5, None, "Control room ref UP-01", ["riot_control", "crowd"]),
    ("PS-ECITY", "Electronic City Police Station", "station",
     77.6693, 12.8465, 5, None, "Control room ref EC-01", ["traffic"]),
    ("HOYSALA-12", "Hoysala 12 (Central)", "patrol_vehicle",
     77.6150, 12.9744, 5, None, "Wireless callsign Hoysala-12", ["first_aid", "riot_control"]),
    ("HOYSALA-27", "Hoysala 27 (North)", "patrol_vehicle",
     77.5934, 13.0290, 5, None, "Wireless callsign Hoysala-27", ["first_aid"]),
    ("CHEETAH-04", "Cheetah 04 (Traffic East)", "traffic_patrol",
     77.6350, 12.9700, 5, None, "Wireless callsign Cheetah-04", ["traffic"]),
    ("CHEETAH-19", "Cheetah 19 (Traffic South)", "traffic_patrol",
     77.6205, 12.9195, 5, None, "Wireless callsign Cheetah-19", ["traffic"]),
    ("CR-BLR", "Bengaluru City Control Room", "control_room",
     77.5900, 12.9700, 5, None, "City control room", ["coordination"]),

    # Dakshina Kannada
    ("PS-MNG-NORTH", "Mangaluru North Police Station", "station",
     74.8447, 12.8712, 24, None, "Control room ref MN-01", ["riot_control", "first_aid"]),
    ("PS-MNG-SOUTH", "Mangaluru South Police Station", "station",
     74.8398, 12.8639, 24, None, "Control room ref MS-01", ["riot_control"]),
    ("PS-KADRI", "Kadri Police Station", "station",
     74.8571, 12.8896, 24, None, "Control room ref KD-01", ["traffic"]),
    ("PS-PANAMBUR", "Panambur Police Station", "station",
     74.8055, 12.9382, 24, None, "Control room ref PB-01", ["first_aid"]),
    ("HOYSALA-DK03", "Hoysala DK-03", "patrol_vehicle",
     74.8500, 12.8660, 24, None, "Wireless callsign Hoysala DK-03", ["first_aid"]),
    ("CHEETAH-DK07", "Cheetah DK-07 (Traffic)", "traffic_patrol",
     74.8562, 12.8601, 24, None, "Wireless callsign Cheetah DK-07", ["traffic"]),

    # Mysuru
    ("PS-DEVARAJA", "Devaraja Police Station", "station",
     76.6520, 12.3085, 22, None, "Control room ref DV-01", ["riot_control", "crowd"]),
    ("PS-KRMOHALLA", "Krishnaraja Mohalla Police Station", "station",
     76.6478, 12.3040, 22, None, "Control room ref KR-01", ["crowd"]),
    ("HOYSALA-MY05", "Hoysala MY-05", "patrol_vehicle",
     76.6540, 12.3150, 22, None, "Wireless callsign Hoysala MY-05", ["first_aid"]),

    # Udupi
    ("PS-UDUPI-TOWN", "Udupi Town Police Station", "station",
     74.7486, 13.3383, 27, None, "Control room ref UT-01", ["crowd", "first_aid"]),
    ("PS-MALPE", "Malpe Police Station", "station",
     74.7062, 13.3489, 27, None, "Control room ref MP-01", ["first_aid"]),

    # Kalaburagi
    ("PS-STATIONBAZAR", "Station Bazar Police Station", "station",
     76.8322, 17.3312, 16, None, "Control room ref SB-01", ["riot_control"]),
    ("PS-CHOWK", "Chowk Police Station", "station",
     76.8272, 17.3364, 16, None, "Control room ref CK-01", ["crowd"]),

    # Uttara Kannada
    ("PS-KARWAR-TOWN", "Karwar Town Police Station", "station",
     74.1281, 14.8145, 28, None, "Control room ref KW-01", ["first_aid", "crowd"]),
)


# --- real demo footage -------------------------------------------------------
# Cameras that have an actual clip behind them, mapped camera code -> filename
# under ``cctv_demo_clip_base_url`` (served from web/public/cctv/).
#
# Two things make a clip-backed camera worth setting up carefully:
#
#   1. The camera's ``DetectorProfile`` below is NARROWED to the class the
#      footage actually shows. The synthetic detector picks a class from the
#      profile, so without this the tile could show a car crash while the alert
#      card says "abandoned object" — the demo would be visibly incoherent, and
#      worse, it would misrepresent what a detection means.
#   2. The hosts were chosen for a high per-window incident rate (the rate is a
#      deterministic function of the camera code), so a single "Run analysis
#      pass" is likely to raise an alert on them rather than needing a dozen
#      clicks. Each pair also sits well inside the 1.5 km corroboration radius of
#      the other camera in its district (~1.1 km in Bengaluru, ~0.7 km in
#      Mangaluru), so the "Nearby cameras" panel has something real to offer.
#
# One pair per demo district, because ``_analytics_enabled_for`` below only
# watches cameras with footage behind them: a district with no clip-backed camera
# reads an honest but empty "Cameras watched 0/n" and can raise nothing at all.
# Dakshina Kannada (24) is the district the wall opens on
# (web/src/stores/useDisasterStore.ts DEFAULT_ASSIGNED_DISTRICT), so it needs a
# watched pair or the landing view of the demo is a blank queue.
CAMERA_DEMO_CLIPS: dict[str, tuple[str, str]] = {
    # camera code:  (clip filename, detection classes the footage supports)
    # --- Bengaluru Urban (5) ---
    "BLR-MGR-04": ("streetfight.mp4", "fight"),
    "BLR-TRC-01": ("accident.mp4", "vehicle_accident"),
    # --- Dakshina Kannada (24) — the district the wall opens on ---
    "MNG-HMP-01": ("streetfight.mp4", "fight"),
    "MNG-CLK-02": ("accident.mp4", "vehicle_accident"),
}


def _clip_url(filename: str) -> str:
    base = (get_settings().cctv_demo_clip_base_url or "/cctv").rstrip("/")
    return f"{base}/{filename}"


def _stream_kind_for(url: str) -> str:
    return "hls" if url.lower().endswith(".m3u8") else "mp4_loop"


def _stream_fields(code: str) -> dict[str, Any]:
    """Resolve the stream columns for one seeded camera.

    Precedence: the camera's own demo clip, then the estate-wide
    ``CCTV_DEMO_STREAM_URL``, then nothing.

    A registered camera with no configured stream is an HONEST state
    (``stream_kind='none'``) — the wall renders an explicit "no stream" panel.
    Faking a video tile would misrepresent what the demo can show.
    """
    clip = CAMERA_DEMO_CLIPS.get(code)
    if clip is not None:
        url = _clip_url(clip[0])
        return {"StreamKind": _stream_kind_for(url), "StreamURL": url}
    url = (get_settings().cctv_demo_stream_url or "").strip()
    if not url:
        return {"StreamKind": "none", "StreamURL": None}
    return {"StreamKind": _stream_kind_for(url), "StreamURL": url}


def _analytics_enabled_for(code: str, status: str) -> bool:
    """Only cameras we can actually SHOW are watched.

    An alert the reviewer cannot look at is not reviewable — they would be
    confirming or dismissing a claim on the strength of a confidence number
    alone. So analytics is enabled only where there is real footage behind the
    camera (``CAMERA_DEMO_CLIPS``) or an estate-wide stream is configured, and
    never on a camera the estate reports as dark.

    The effect on the wall is deliberate: "Cameras watched 2/22" is the honest
    reading of this demo, rather than 20 cameras raising alerts into blank tiles.
    Drop another clip into CAMERA_DEMO_CLIPS and that camera joins the watch set.
    """
    if status not in ("online", "degraded"):
        return False
    if code in CAMERA_DEMO_CLIPS:
        return True
    return bool((get_settings().cctv_demo_stream_url or "").strip())


def _retire_unwatched_alerts(repo: CctvRepo, actor: str) -> int:
    """Soft-delete open alerts on cameras that are no longer being watched.

    Re-seeding narrows the watch set, but alerts raised earlier on a now-unwatched
    camera would linger in the queue pointing at a blank tile. Detections are
    append-only and stay exactly as recorded; only the reviewable ALERT is
    withdrawn, and the withdrawal is audited rather than silent.
    """
    watched = {int(c["CameraID"]) for c in repo.list("Camera")
               if c.get("AnalyticsEnabled")}
    retired = 0
    for alert in repo.list("CctvAlert"):
        if int(alert.get("CameraID") or 0) in watched:
            continue
        # Leave decided alerts alone — a dismissal or a dispatch is history.
        if alert.get("Status") not in ("proposed", "confirmed"):
            continue
        aid = int(alert["CctvAlertID"])
        for d in repo.list("CctvDispatch", where={"CctvAlertID": aid}):
            if d.get("Status") == "proposed":
                repo.update("CctvDispatch", int(d["CctvDispatchID"]), {
                    "Status": "cancelled", "CancelledAt": _now(),
                    "Version": int(d.get("Version") or 1) + 1})
        repo.soft_delete("CctvAlert", aid)
        repo.append_activity("alert", aid, actor=actor, action="alert.withdrawn",
                             diff={"cause": "camera is no longer watched",
                                   "camera_id": alert.get("CameraID"),
                                   "alert_type": alert.get("AlertType")})
        retired += 1
    return retired


def seed_demo_estate(*, repo: Optional[CctvRepo] = None,
                     actor: str = "demo.seed") -> dict[str, int]:
    """Upsert the camera estate + responders. Idempotent by ``Code``.

    Returns per-table counts of rows written.
    """
    repo = repo or cctv_repo()
    counts = {"Camera": 0, "PatrolUnit": 0}
    clipped = 0

    for (code, name, label, lon, lat, district_id, unit_id, bearing, status,
         profile) in _CAMERAS:
        clip = CAMERA_DEMO_CLIPS.get(code)
        if clip is not None:
            # Constrain the detector to what the footage actually shows, so the
            # alert on the card always matches the scene in the tile.
            profile = clip[1]
            clipped += 1
        fields = {
            "Code": code, "Name": name, "LocationLabel": label,
            "Lon": lon, "Lat": lat, "BearingDegrees": bearing, "FovDegrees": 72.0,
            "DistrictID": district_id, "UnitID": unit_id,
            "Status": status,
            "AnalyticsEnabled": _analytics_enabled_for(code, status),
            "DetectorProfile": profile or None,
            # A clip-backed camera loops actual incident footage, so the incident
            # is on screen in every window — flag it every pass rather than making
            # the operator click until a probability lands.
            "SceneIsContinuous": clip is not None,
            "LastHeartbeatAt": (_now() if status in ("online", "degraded") else None),
            "Notes": None,
            **_stream_fields(code),
        }
        existing = repo.find_one("Camera", {"Code": code})
        if existing:
            repo.update("Camera", int(existing["CameraID"]), fields)
        else:
            repo.create("Camera", fields)
        counts["Camera"] += 1

    for (code, name, kind, lon, lat, district_id, unit_id, contact, caps) in _RESPONDERS:
        fields = {
            "Code": code, "Name": name, "Kind": kind,
            "UnitID": unit_id, "DistrictID": district_id,
            "Lon": lon, "Lat": lat, "Status": "available",
            "ContactLabel": contact, "Capabilities": list(caps),
            "LastUpdatedAt": _now(),
        }
        existing = repo.find_one("PatrolUnit", {"Code": code})
        if existing:
            repo.update("PatrolUnit", int(existing["PatrolUnitID"]), fields)
        else:
            repo.create("PatrolUnit", fields)
        counts["PatrolUnit"] += 1

    repo.reseed_counters()
    # Withdraw anything left in the queue for a camera that is no longer watched.
    retired = _retire_unwatched_alerts(repo, actor)
    repo.append_activity("camera", 0, actor=actor, action="estate.seeded",
                         diff={"cameras": counts["Camera"],
                               "responders": counts["PatrolUnit"],
                               "cameras_with_footage": clipped,
                               "alerts_withdrawn": retired,
                               "estate_stream_configured":
                                   bool((get_settings().cctv_demo_stream_url or "").strip())})
    counts["CamerasWithFootage"] = clipped
    counts["AlertsWithdrawn"] = retired
    return counts
