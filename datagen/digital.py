"""Synthetic digital inputs: devices, artifacts, communication + location events.

All identifiers are unmistakably synthetic. Communication/location rows link
canonical entities and carry provenance (SourceRecordID) + review state; they are
for aggregate/reviewed analytics only and never imply guilt.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from .db import Geom, Json
from .identity import IdentityBuilder
from . import v2common as C

C.register("Device", [
    "DeviceID", "CanonicalEntityID", "CaseMasterID", "DeviceType",
    "SyntheticIdentifier", "Label", "SourceRecordID",
])
C.register("DeviceArtifact",
           ["DeviceID", "ArtifactType", "SyntheticReference", "Detail", "EvidenceItemID"])
C.register("CommunicationEvent", [
    "CaseMasterID", "FromCanonicalEntityID", "ToCanonicalEntityID", "CommType",
    "OccurredAt", "DurationSec", "SyntheticEndpointA", "SyntheticEndpointB",
    "ReviewStatus", "SourceRecordID",
])
C.register("LocationObservation", [
    "CanonicalEntityID", "CaseMasterID", "ObservedAt", "geom", "DistrictID",
    "Source", "SourceRecordID",
])
C.register("DigitalImportBatch",
           ["IngestionJobID", "BatchKind", "RowCount", "DryRun", "Status"])


def build_case_digital(world: C.World, ib: IdentityBuilder, *, case_id: int,
                       accused_cpids: List[int], reg_date: dt.date,
                       lon: float, lat: float, district_id: int,
                       source_record_id: Optional[int],
                       want_comm: int = 0, want_location: int = 0,
                       want_device: bool = False) -> None:
    w = world
    rng = w.rng
    base = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 8, 0)

    # phone entities for participating persons (canonical non-person entities)
    phone_entities: List[int] = []
    for cpid in accused_cpids[:3]:
        ph = C.synth_token("PHONE", cpid * 7 + 1)
        eid = ib.mint_nonperson_entity("phone", ph, {"owner_person": cpid})
        phone_entities.append(eid)

    if want_device and accused_cpids:
        ent = w.person_entity.get(accused_cpids[0])
        dev_id = w.next_id("Device")
        w.add("Device", (dev_id, ent, case_id, "mobile",
                         C.synth_token("IMEI", dev_id), "Seized handset", source_record_id))
        w.add("DeviceArtifact", (dev_id, "chat", C.synth_token("CHAT", dev_id),
                                 Json({"synthetic": True, "messages": 3}), None))
        w.cover("device_artifact")

    for i in range(want_comm):
        if len(phone_entities) >= 2:
            a, b = phone_entities[0], phone_entities[1 + (i % (len(phone_entities) - 1))]
        else:
            a = phone_entities[0] if phone_entities else None
            b = None
        occurred = base + dt.timedelta(hours=i)
        w.add("CommunicationEvent", (
            case_id, a, b, "call" if i % 2 == 0 else "sms",
            occurred.strftime("%Y-%m-%d %H:%M:%S+00"),
            int(rng.g.integers(10, 900)),
            C.synth_token("MSISDN", (case_id * 13 + i)),
            C.synth_token("MSISDN", (case_id * 17 + i + 1)),
            "reviewed" if rng.bernoulli(0.5) else "candidate", source_record_id,
        ))
        w.cover("communication_event")

    for i in range(want_location):
        ent = phone_entities[0] if phone_entities else (
            w.person_entity.get(accused_cpids[0]) if accused_cpids else None)
        observed = base + dt.timedelta(hours=i, minutes=int(rng.g.integers(0, 59)))
        # use the (in-state, in-district) incident coordinate to stay valid
        w.add("LocationObservation", (
            ent, case_id, observed.strftime("%Y-%m-%d %H:%M:%S+00"),
            Geom.point(lon, lat), district_id, "synthetic_gps", source_record_id,
        ))
        w.cover("location_observation")
