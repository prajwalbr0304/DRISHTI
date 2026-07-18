"""Canonical, provenance-backed financial sub-graph (reuses legacy tables).

Accounts carry their canonical person/entity in Attributes; transactions carry a
SourceRecord in Properties and an EvidenceCaseID; reviewed case links live in
TransactionLink. Money patterns (structuring / fan-in / layering) are rule-based
with an explicit reason code — never an implication of guilt.

Phase 8 additions: every account/transaction carries a normalised currency and
channel, a synthetic reference, a review state (candidate until reviewed) and an
IsSynthetic flag, so a regenerated golden fixture matches the Phase-8 schema.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from .db import Json
from . import v2common as C

# Phase 8 columns are appended so a regenerated fixture carries currency /
# normalised channel / review state / synthetic reference / synthetic flag.
C.register("FinancialAccount", [
    "AccountID", "AccountNo", "AccountType", "HolderName", "EntityID", "Bank",
    "IFSC", "IsFlagged", "Attributes", "Currency", "IsSynthetic",
])
C.register("FinancialTransaction", [
    "TransactionID", "SourceAccountID", "DestinationAccountID", "Amount",
    "TxnTimestamp", "Channel", "IsFlagged", "FlagReason", "EvidenceCaseID",
    "Properties", "Currency", "NormalizedChannel", "ReviewStatus",
    "SyntheticReference", "IsSynthetic",
])
C.register("TransactionLink",
           ["TransactionID", "CaseMasterID", "LinkType", "Confidence", "ReviewStatus"])

_BANKS = ["State Bank", "Canara Bank", "HDFC", "ICICI", "Axis", "Union Bank"]

# Normalised channel vocabulary (mirrors app/imports/templates.normalize_channel).
_CHANNEL_NORM = {
    "upi": "upi", "imps": "imps", "neft": "neft", "rtgs": "rtgs",
    "cash": "cash", "atm": "atm", "wallet": "wallet", "card": "card",
}


def _norm_channel(channel: str) -> str:
    return _CHANNEL_NORM.get((channel or "").lower(), "unknown")


def build_case_financial(world: C.World, *, case_id: int, holder_cpids: List[int],
                         reg_date: dt.date, source_record_id: Optional[int],
                         pattern: str) -> None:
    """Create a small money trail for an economic/organised case.

    ``pattern`` is one of: structuring (repeated sub-threshold deposits),
    fan_in (consolidation from many mules), layering (multi-hop pass-through
    chain). Each flagged transaction carries an explicit reason code.
    """
    w = world
    rng = w.rng
    base = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 10, 0)

    def mk_account(cpid: Optional[int], atype: str, flagged: bool) -> int:
        aid = w.next_id("FinancialAccount")
        label = w.person_label.get(cpid, "Account Holder") if cpid else "Mule Holder"
        w.add("FinancialAccount", (
            aid, C.synth_token("ACCT", aid), atype, label, None,
            rng.choice(_BANKS), C.synth_token("IFSC", aid % 9999), flagged,
            Json({"canonical_person_id": cpid, "synthetic": True}), "INR", True,
        ))
        return aid

    def mk_txn(src: int, dst: int, amount: float, when: dt.datetime, channel: str,
               reason: str, note: str) -> int:
        tid = w.next_id("FinancialTransaction")
        w.add("FinancialTransaction", (
            tid, src, dst, round(float(amount), 2),
            when.strftime("%Y-%m-%d %H:%M:%S+00"), channel, True, reason, case_id,
            Json({"source_record_id": source_record_id, "reason": note, "pattern": reason}),
            "INR", _norm_channel(channel), "candidate", C.synth_token("TXNREF", tid), True,
        ))
        return tid

    victim_acct = mk_account(holder_cpids[0] if holder_cpids else None, "savings", False)
    mule_accts = [mk_account(holder_cpids[i % len(holder_cpids)] if holder_cpids else None,
                             "mule", True) for i in range(2)]

    txn_ids: List[int] = []
    if pattern == "structuring":
        # smurfing: 6 sub-threshold deposits (>= 0.6 x the 50k reporting threshold)
        # into ONE mule hub within a short window — the shape the rule detects.
        hub = mule_accts[0]
        for i in range(6):
            smurf = mk_account(None, "savings", False)
            txn_ids.append(mk_txn(
                smurf, hub, float(rng.g.uniform(31000, 49000)),
                base + dt.timedelta(hours=i * 4), "imps", "structuring", "sub-threshold smurf"))
        w.cover("financial_structuring")
    elif pattern == "layering":
        # multi-hop pass-through chain: victim -> conduit1 -> conduit2 -> cashout
        conduit1 = mule_accts[0]
        conduit2 = mule_accts[1]
        cashout = mk_account(None, "current", True)
        amt = float(rng.g.uniform(150000, 400000))
        txn_ids.append(mk_txn(victim_acct, conduit1, amt, base, "neft", "layering", "placement"))
        txn_ids.append(mk_txn(conduit1, conduit2, amt * 0.98, base + dt.timedelta(hours=3),
                              "rtgs", "layering", "pass-through"))
        txn_ids.append(mk_txn(conduit2, cashout, amt * 0.95, base + dt.timedelta(hours=6),
                              "rtgs", "layering", "cash-out"))
        w.cover("financial_layering")
    else:  # fan_in / consolidation
        for i in range(3):
            txn_ids.append(mk_txn(
                mule_accts[i % 2], victim_acct, float(rng.g.uniform(20000, 300000)),
                base + dt.timedelta(hours=i * 2), "neft", "fan_in", "consolidation"))
        w.cover("financial_fan_in")

    # reviewed link of the first transaction to the case (evidence-backed)
    if txn_ids:
        w.add("TransactionLink", (txn_ids[0], case_id, "evidence", 0.80, "reviewed"))
        w.cover("financial_reviewed_link")
