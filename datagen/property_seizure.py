"""Seizures + property/vehicle/weapon/substance items (form-entered metadata)."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from .db import Json
from . import v2common as C

C.register("Seizure", [
    "SeizureID", "CaseMasterID", "CaseEventID", "SeizureType", "SeizedAt",
    "Place", "MemoEvidenceItemID", "Actor",
])
C.register("PropertyItem", [
    "PropertyItemID", "SeizureID", "CaseMasterID", "ItemType",
    "SyntheticIdentifier", "Description", "Quantity", "Unit", "EstimatedValue",
    "OwnerCanonicalPersonID", "Status", "VehicleFields", "WeaponFields",
])

_VEHICLE_TYPES = ["Motorcycle", "Car", "Auto-rickshaw", "Lorry", "SUV"]
_WEAPONS = ["knife", "machete", "iron rod", "country pistol"]
_SUBSTANCES = ["ganja", "contraband liquor", "psychotropic tablets"]
_DOCUMENTS = ["forged agreement", "seized ledger", "synthetic ID document", "bank passbook"]


def build_case_property(world: C.World, *, case_id: int, reg_date: dt.date,
                        item_types: List[str], owner_cpid: Optional[int],
                        actor: str = "io_demo") -> None:
    w = world
    rng = w.rng
    if not item_types:
        return
    seized = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 12, 0)
    sz_id = w.next_id("Seizure")
    w.add("Seizure", (sz_id, case_id, None, "seizure",
                      seized.strftime("%Y-%m-%d %H:%M:%S+00"), "Scene of offence",
                      None, actor))
    w.cover("property_seizure")

    for itype in item_types:
        pid = w.next_id("PropertyItem")
        ident = C.synth_token("PROP", pid)
        vehicle_fields: dict = {}
        weapon_fields: dict = {}
        desc = "Recovered property"
        qty, unit, value = 1, "count", round(float(rng.g.uniform(500, 200000)), 2)
        if itype == "vehicle":
            vt = rng.choice(_VEHICLE_TYPES)
            vehicle_fields = {
                "vehicle_type": vt,
                "registration": C.synth_token("KA-REG", pid),
                "chassis": C.synth_token("CHS", pid),
                "engine": C.synth_token("ENG", pid),
            }
            desc = f"{vt} (synthetic registration)"
            w.cover("vehicle_item")
        elif itype == "weapon":
            weapon_fields = {"weapon": rng.choice(_WEAPONS),
                             "seal_no": C.synth_token("SEAL", pid)}
            desc = f"Weapon: {weapon_fields['weapon']}"
            w.cover("weapon_item")
        elif itype == "substance":
            desc = f"Seized substance: {rng.choice(_SUBSTANCES)}"
            qty, unit = round(float(rng.g.uniform(5, 5000)), 2), "grams"
            w.cover("substance_item")
        elif itype == "document":
            desc = f"Seized document: {rng.choice(_DOCUMENTS)}"
            unit = "count"
            w.cover("document_item")
        # golden coverage across the full disposal lifecycle, not just seized/recovered
        status = rng.choice(["seized", "seized", "recovered", "returned", "disposed"])
        w.add("PropertyItem", (
            pid, sz_id, case_id, itype, ident, desc, qty, unit, value,
            owner_cpid, status, Json(vehicle_fields), Json(weapon_fields),
        ))
