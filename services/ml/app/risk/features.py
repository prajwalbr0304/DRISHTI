"""Per-offender feature builder + (synthetic) supervised label.

Assembles one feature row per EntityGraph 'person' offender from the graph,
gang, financial and district-context tables. Also derives an ordinal risk label
(0..4) from a NOISY latent function of the features — this stands in for the
expert/historical labels TabFM consumes as in-context examples (in production the
label would be an outcome such as 'reoffended within 12 months'). The noise makes
the mapping features->label genuinely probabilistic, so model calibration is
meaningful rather than trivial.
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES = [
    "career_offenses", "specialty_severity", "juvenile", "gang_role_rank",
    "pagerank", "betweenness", "degree", "community_size",
    "has_flagged_financial", "hidden_assoc_count", "district_crime_rate",
]

# Human-readable labels for the gauge + factor-bars widget.
FEATURE_LABELS = {
    "career_offenses": "prior offences",
    "specialty_severity": "offence severity",
    "juvenile": "juvenile record",
    "gang_role_rank": "gang seniority",
    "pagerank": "network influence",
    "betweenness": "network brokerage",
    "degree": "connections",
    "community_size": "cluster size",
    "has_flagged_financial": "flagged finances",
    "hidden_assoc_count": "hidden associations",
    "district_crime_rate": "district crime rate",
}

RISK_BANDS = ["Low", "Guarded", "Elevated", "High", "Severe"]

_GANG_ROLE_RANK = {"suspect": 1, "associate": 2, "core": 3, "financier": 4, "leader": 5}

# specialty (crime sub-head) -> severity 0..3
_SPECIALTY_SEVERITY = {
    "Murder": 3, "Attempt to Murder": 3, "Rape": 3, "Kidnapping": 3,
    "Human Trafficking": 3, "Dacoity": 3, "Drug Trafficking": 3, "Smuggling": 3,
    "Robbery": 2, "Burglary": 2, "Grievous Hurt": 2, "Assault": 2,
    "Molestation": 2, "Drug Peddling": 2, "Rioting": 2, "Bank Fraud": 2,
    "Dowry Harassment": 2, "Hit and Run": 2,
    "Theft": 1, "Vehicle Theft": 1, "Cheating": 1, "Cyber Fraud": 1,
    "OTP Scam": 1, "Illicit Liquor": 1, "Drunk Driving": 1, "Missing Person": 0,
}

# latent-risk weights (domain-sensible; used only to synthesise the label)
_LABEL_WEIGHTS = {
    "career_offenses": 1.4, "specialty_severity": 1.0, "gang_role_rank": 0.9,
    "betweenness": 0.7, "has_flagged_financial": 0.8, "hidden_assoc_count": 0.4,
    "pagerank": 0.5, "district_crime_rate": 0.3, "juvenile": 0.2, "degree": 0.2,
    "community_size": -0.1,
}
# skewed class cut-points (percentiles) so 'Severe' is genuinely rare
_LABEL_PERCENTILES = [25, 52, 77, 92]


def _district_crime_rate(conn) -> dict[str, float]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT d."DistrictName", COUNT(*)::float / NULLIF(MAX(s."Population"),0) * 100000 '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'LEFT JOIN "SocialIndicator" s ON s."DistrictID"=d."DistrictID" '
            'GROUP BY d."DistrictName"')
        return {r[0]: float(r[1]) if r[1] is not None else 0.0 for r in cur.fetchall()}


def _district_ids(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictName","DistrictID" FROM "District"')
        return {r[0]: int(r[1]) for r in cur.fetchall()}


def build(conn, seed: int = 42) -> dict:
    """Return dict with X (n,f), y (n,), entity_ids, meta (per-offender dicts)."""
    rng = np.random.default_rng(seed)
    dcr = _district_crime_rate(conn)
    dids = _district_ids(conn)

    with conn.cursor() as cur:
        # gang role per member entity
        cur.execute('SELECT "MemberEntityID", MAX("Role"::text) FROM "GangMembership" '
                    'WHERE "MemberEntityID" IS NOT NULL GROUP BY "MemberEntityID"')
        role = {int(r[0]): _GANG_ROLE_RANK.get(r[1], 0) for r in cur.fetchall()}
        # network degree
        cur.execute('SELECT e, COUNT(*) FROM (SELECT "Source" e FROM "NetworkEdge" '
                    'UNION ALL SELECT "Target" FROM "NetworkEdge") t GROUP BY e')
        degree = {int(r[0]): int(r[1]) for r in cur.fetchall()}
        # community sizes
        cur.execute("SELECT (\"Attributes\"->>'community')::int, COUNT(*) FROM \"EntityGraph\" "
                    "WHERE \"Attributes\" ? 'community' GROUP BY 1")
        comm_size = {int(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}
        # flagged financial accounts
        cur.execute('SELECT DISTINCT "EntityID" FROM "FinancialAccount" '
                    'WHERE "EntityID" IS NOT NULL AND "IsFlagged"')
        flagged = {int(r[0]) for r in cur.fetchall()}
        # hidden-association appearances
        cur.execute('SELECT e, COUNT(*) FROM (SELECT "EntityA" e FROM "drishti_hidden_associations" '
                    'UNION ALL SELECT "EntityB" FROM "drishti_hidden_associations") t GROUP BY e')
        hidden = {int(r[0]): int(r[1]) for r in cur.fetchall()}
        # entity -> representative accused via CANONICAL identity (Phase 4; no name
        # matching): EntityGraph.CanonicalEntityID -> CanonicalEntity.CanonicalPersonID
        # -> CasePartyRole(accused) -> Accused (LegacyRefID). One representative
        # AccusedMasterID per person node is enough for the explain/provenance link.
        cur.execute("""
            SELECT eg."EntityID", MIN(r."LegacyRefID") AS accused_master_id
            FROM "EntityGraph" eg
            JOIN "CanonicalEntity" ce ON ce."CanonicalEntityID" = eg."CanonicalEntityID"
            JOIN "CasePartyRole" r ON r."CanonicalPersonID" = ce."CanonicalPersonID"
                AND r."RoleType" = 'accused' AND r."LegacyRefTable" = 'Accused'
                AND r."LegacyRefID" IS NOT NULL
            WHERE eg."EntityType" = 'person'
            GROUP BY eg."EntityID" """)
        accused_map = {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in cur.fetchall()}
        # the offenders themselves
        cur.execute("""
            SELECT "EntityID","Label","Attributes"
            FROM "EntityGraph" WHERE "EntityType"='person' ORDER BY "EntityID" """)
        offenders = cur.fetchall()

    entity_ids, rows, meta = [], [], []
    for eid, label, attrs in offenders:
        eid = int(eid)
        attrs = attrs or {}
        home = attrs.get("home_district")
        feat = {
            "career_offenses": float(attrs.get("career_offenses", 0) or 0),
            "specialty_severity": float(_SPECIALTY_SEVERITY.get(attrs.get("specialty"), 1)),
            "juvenile": 1.0 if attrs.get("juvenile") else 0.0,
            "gang_role_rank": float(role.get(eid, 0)),
            "pagerank": float(attrs.get("pagerank", 0.0) or 0.0),
            "betweenness": float(attrs.get("betweenness", 0.0) or 0.0),
            "degree": float(degree.get(eid, 0)),
            "community_size": float(comm_size.get(attrs.get("community"), 0)),
            "has_flagged_financial": 1.0 if eid in flagged else 0.0,
            "hidden_assoc_count": float(hidden.get(eid, 0)),
            "district_crime_rate": float(dcr.get(home, 0.0)),
        }
        entity_ids.append(eid)
        rows.append([feat[f] for f in FEATURE_NAMES])
        meta.append({"entity_id": eid, "name": label, "home_district": home,
                     "district_id": dids.get(home), "accused_master_id": accused_map.get(eid),
                     "gang_role_rank": int(role.get(eid, 0))})

    X = np.array(rows, dtype=float)
    y = _synthesise_labels(X, rng)
    return {"X": X, "y": y, "entity_ids": entity_ids, "meta": meta,
            "feature_names": FEATURE_NAMES}


def _zscore(X):
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    return (X - mu) / sd, mu, sd


def _synthesise_labels(X, rng):
    z, _, _ = _zscore(X)
    w = np.array([_LABEL_WEIGHTS[f] for f in FEATURE_NAMES])
    latent = z @ w + rng.normal(0, 1.0, size=len(X))   # substantial noise
    cuts = np.percentile(latent, _LABEL_PERCENTILES)
    return np.digitize(latent, cuts).astype(int)        # 0..4
