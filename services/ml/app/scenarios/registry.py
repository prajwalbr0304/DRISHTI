"""Deterministic crypto / dark-web / cross-jurisdiction scenario registry
(Prompt 20 Part A) — pure data + pure functions, no DB, no network.

Design rules enforced by validate():
  * jurisdiction scope is a SEPARATE governed dimension from crime type;
  * every scenario is explicitly synthetic; dark-web scenarios are a manually
    classified source with live_collection=False (no scraping/purchase/creds);
  * entities are typed (person / wallet_ref / exchange_account / device / phone /
    vehicle / location / case / source_record) and every edge is typed with a
    basis of "evidence-backed" or "hypothetical";
  * every governed jurisdiction scope value and crime family is covered.
"""
from __future__ import annotations

from typing import Optional

# --- governed jurisdiction scope (separate from crime type) ----------------
JURISDICTION_SCOPES: dict[str, dict] = {
    "local": {"label": "Local", "kn": "ಸ್ಥಳೀಯ",
              "desc": "Confined to a single police station / jurisdiction."},
    "inter_district": {"label": "Inter-district", "kn": "ಅಂತರ-ಜಿಲ್ಲಾ",
                       "desc": "Spans two or more districts within Karnataka."},
    "inter_state": {"label": "Inter-state", "kn": "ಅಂತರ-ರಾಜ್ಯ",
                    "desc": "Involves another Indian state; may need coordination."},
    "national": {"label": "National", "kn": "ರಾಷ್ಟ್ರೀಯ",
                 "desc": "Nation-wide footprint; central-agency referral likely."},
    "international": {"label": "International", "kn": "ಅಂತರರಾಷ್ಟ್ರೀಯ",
                      "desc": "Actors/servers/funds abroad; MLAT/Interpol channels."},
    "cross_border": {"label": "Cross-border", "kn": "ಗಡಿಯಾಚೆಗಿನ",
                     "desc": "Movement across a national land/sea border."},
}

# --- crime families this registry adds to the taxonomy ---------------------
CRIME_FAMILIES: dict[str, dict] = {
    "crypto_fraud": {"label": "Cryptocurrency-enabled fraud", "head": "Economic & Cyber Crime",
                     "kn": "ಕ್ರಿಪ್ಟೋ ವಂಚನೆ"},
    "crypto_extortion": {"label": "Cryptocurrency-enabled extortion", "head": "Economic & Cyber Crime",
                         "kn": "ಕ್ರಿಪ್ಟೋ ಸುಲಿಗೆ"},
    "crypto_money_movement": {"label": "Cryptocurrency money movement / layering",
                              "head": "Economic & Cyber Crime", "kn": "ಕ್ರಿಪ್ಟೋ ಹಣ ವರ್ಗಾವಣೆ"},
    "darkweb_contraband": {"label": "Dark-web-enabled contraband (manually classified)",
                           "head": "Economic & Cyber Crime", "kn": "ಡಾರ್ಕ್‌ವೆಬ್ ಕಳ್ಳಸಾಗಣೆ"},
    "darkweb_fraud": {"label": "Dark-web-enabled fraud / stolen-data trade (manually classified)",
                      "head": "Economic & Cyber Crime", "kn": "ಡಾರ್ಕ್‌ವೆಬ್ ವಂಚನೆ"},
    "cross_jurisdiction": {"label": "Cross-jurisdiction organised activity",
                           "head": "Economic & Cyber Crime", "kn": "ಅಂತರ-ವ್ಯಾಪ್ತಿ ಅಪರಾಧ"},
}

ENTITY_TYPES = ("person", "wallet_ref", "exchange_account", "device", "phone",
                "vehicle", "location", "case", "source_record")
EDGE_BASES = ("evidence-backed", "hypothetical")


def _n(node_id: str, kind: str, label: str, **attrs) -> dict:
    return {"id": node_id, "type": kind, "label": label, "attrs": attrs}


def _e(src: str, rel: str, dst: str, basis: str, note: str = "") -> dict:
    return {"source": src, "rel": rel, "target": dst, "basis": basis, "note": note}


# ---------------------------------------------------------------------------
# The scenarios. Deterministic, ordered, clearly synthetic. Every wallet /
# account / phone value is an obvious SYN placeholder, never a real identifier.
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "scenario_id": "P20-CRYPTO-001",
        "title": "USDT investment-app fraud drains victims across three districts",
        "crime_family": "crypto_fraud", "crime_subtype": "Cryptocurrency Fraud",
        "jurisdiction_scope": "inter_district", "gravity": "Serious",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: victims in Bengaluru City, Mysuru and Tumakuru were "
                    "induced to deposit into a fake USDT trading app; funds were swept "
                    "to a synthetic wallet cluster."),
        "districts": ["Bengaluru City", "Mysuru", "Tumakuru"],
        "entities": [
            _n("p_org1", "person", "Synthetic accused (app operator)"),
            _n("w_usdt1", "wallet_ref", "SYN-WALLET-USDT-0001", chain="tron-synthetic"),
            _n("ex_a1", "exchange_account", "SYN-EXCH-ACC-0001", exchange="synthetic-exchange"),
            _n("ph1", "phone", "SYN-PHONE-900000001"),
            _n("loc1", "location", "Bengaluru City"),
            _n("c1", "case", "SYN-FIR-CRYPTO-001"),
        ],
        "edges": [
            _e("p_org1", "controls", "w_usdt1", "hypothetical", "wallet control inferred, not confirmed"),
            _e("p_org1", "uses", "ph1", "evidence-backed", "number in complaint"),
            _e("w_usdt1", "cashed_out_via", "ex_a1", "evidence-backed", "on-chain to exchange deposit (synthetic)"),
            _e("c1", "reported_at", "loc1", "evidence-backed"),
        ],
        "referral": None,
        "nl_examples": [
            {"lang": "en", "q": "Show cryptocurrency fraud cases across districts in the last 90 days"},
            {"lang": "kn", "q": "ಕಳೆದ 90 ದಿನಗಳಲ್ಲಿ ಜಿಲ್ಲೆಗಳಾದ್ಯಂತ ಕ್ರಿಪ್ಟೋ ವಂಚನೆ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ"},
        ],
    },
    {
        "scenario_id": "P20-CRYPTO-002",
        "title": "Sextortion demanding Bitcoin from a single-station complainant",
        "crime_family": "crypto_extortion", "crime_subtype": "Crypto Extortion",
        "jurisdiction_scope": "local", "gravity": "Serious",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: a complainant received threats demanding Bitcoin to a "
                    "synthetic wallet; confined to one station's jurisdiction."),
        "districts": ["Dakshina Kannada"],
        "entities": [
            _n("p_susp2", "person", "Synthetic suspect (unknown)"),
            _n("w_btc2", "wallet_ref", "SYN-WALLET-BTC-0002", chain="bitcoin-synthetic"),
            _n("ph2", "phone", "SYN-PHONE-900000002"),
            _n("dev2", "device", "SYN-DEVICE-IMEI-0002"),
            _n("c2", "case", "SYN-FIR-CRYPTO-002"),
        ],
        "edges": [
            _e("p_susp2", "demanded_payment_to", "w_btc2", "evidence-backed", "wallet in threat message"),
            _e("p_susp2", "contacted_via", "ph2", "evidence-backed"),
            _e("ph2", "linked_to", "dev2", "hypothetical", "handset linkage unconfirmed"),
        ],
        "referral": None,
        "nl_examples": [
            {"lang": "en", "q": "How many crypto extortion cases were reported this month?"},
            {"lang": "kn", "q": "ಈ ತಿಂಗಳು ಎಷ್ಟು ಕ್ರಿಪ್ಟೋ ಸುಲಿಗೆ ಪ್ರಕರಣಗಳು ವರದಿಯಾಗಿವೆ?"},
        ],
    },
    {
        "scenario_id": "P20-CRYPTO-003",
        "title": "Layering scam proceeds through wallets to an overseas exchange",
        "crime_family": "crypto_money_movement", "crime_subtype": "Crypto Money Laundering",
        "jurisdiction_scope": "international", "gravity": "Heinous",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: proceeds of an OTP scam were layered across synthetic "
                    "wallets and cashed out at an exchange registered abroad; flagged "
                    "for FIU/MLAT coordination."),
        "districts": ["Bengaluru City"],
        "entities": [
            _n("p_mule3", "person", "Synthetic money mule"),
            _n("w_hop3a", "wallet_ref", "SYN-WALLET-HOP-0003A"),
            _n("w_hop3b", "wallet_ref", "SYN-WALLET-HOP-0003B"),
            _n("ex_intl3", "exchange_account", "SYN-EXCH-INTL-0003", jurisdiction="overseas-synthetic"),
            _n("acct3", "exchange_account", "SYN-BANK-ACC-0003"),
            _n("c3", "case", "SYN-FIR-CRYPTO-003"),
        ],
        "edges": [
            _e("acct3", "converted_to_crypto", "w_hop3a", "evidence-backed"),
            _e("w_hop3a", "hopped_to", "w_hop3b", "evidence-backed", "on-chain hop (synthetic)"),
            _e("w_hop3b", "cashed_out_via", "ex_intl3", "hypothetical", "attribution pending MLAT"),
            _e("p_mule3", "operates", "acct3", "evidence-backed"),
        ],
        "referral": {"from": "state_police", "to": "FIU-IND (synthetic)", "kind": "financial_intelligence"},
        "nl_examples": [
            {"lang": "en", "q": "List international cryptocurrency money-laundering cases flagged for referral"},
            {"lang": "kn", "q": "ಉಲ್ಲೇಖಕ್ಕಾಗಿ ಗುರುತಿಸಲಾದ ಅಂತರರಾಷ್ಟ್ರೀಯ ಕ್ರಿಪ್ಟೋ ಹಣ ವರ್ಗಾವಣೆ ಪ್ರಕರಣಗಳನ್ನು ಪಟ್ಟಿ ಮಾಡಿ"},
        ],
    },
    {
        "scenario_id": "P20-CRYPTO-004",
        "title": "National fake-token investment scam network",
        "crime_family": "crypto_fraud", "crime_subtype": "Crypto Investment Scam",
        "jurisdiction_scope": "national", "gravity": "Serious",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: a fake-token 'guaranteed returns' scheme with victims "
                    "reported in multiple states; a coordinated network of promoters."),
        "districts": ["Bengaluru City", "Belagavi"],
        "entities": [
            _n("p_prom4", "person", "Synthetic promoter"),
            _n("w_token4", "wallet_ref", "SYN-WALLET-TOKEN-0004"),
            _n("ph4", "phone", "SYN-PHONE-900000004"),
            _n("c4", "case", "SYN-FIR-CRYPTO-004"),
        ],
        "edges": [
            _e("p_prom4", "promoted", "w_token4", "evidence-backed"),
            _e("p_prom4", "recruited_via", "ph4", "hypothetical"),
        ],
        "referral": {"from": "state_police", "to": "other_state_police (synthetic)", "kind": "inter_state_coordination"},
        "nl_examples": [
            {"lang": "en", "q": "Show national crypto investment scam networks"},
            {"lang": "kn", "q": "ರಾಷ್ಟ್ರೀಯ ಕ್ರಿಪ್ಟೋ ಹೂಡಿಕೆ ವಂಚನೆ ಜಾಲಗಳನ್ನು ತೋರಿಸಿ"},
        ],
    },
    {
        "scenario_id": "P20-DARKWEB-001",
        "title": "Dark-web marketplace contraband listing (manually classified)",
        "crime_family": "darkweb_contraband", "crime_subtype": "Dark Web Contraband",
        "jurisdiction_scope": "cross_border", "gravity": "Heinous",
        "source_classification": "manual", "live_collection": False,
        "summary": ("Synthetic: an FIR references a dark-web marketplace listing shipping "
                    "contraband across a border. Source is MANUALLY classified from the "
                    "complaint; DRISHTI performs no scraping, purchase or credential use."),
        "districts": ["Kalaburagi"],
        "entities": [
            _n("p_vendor_d1", "person", "Synthetic vendor handle (pseudonymous)"),
            _n("src_d1", "source_record", "SYN-SRC-DARKWEB-0001", classification="manual", live_collection=False),
            _n("w_xmr_d1", "wallet_ref", "SYN-WALLET-XMR-0001", chain="monero-synthetic"),
            _n("loc_d1", "location", "Kalaburagi (border transit)"),
            _n("c_d1", "case", "SYN-FIR-DARKWEB-001"),
        ],
        "edges": [
            _e("src_d1", "manually_classified_as", "c_d1", "evidence-backed",
               "analyst classification of the complaint; no live collection"),
            _e("p_vendor_d1", "settled_in", "w_xmr_d1", "hypothetical", "privacy-coin attribution unconfirmed"),
            _e("c_d1", "transit_through", "loc_d1", "hypothetical"),
        ],
        "referral": {"from": "state_police", "to": "NCB / Customs (synthetic)", "kind": "cross_border_contraband"},
        "nl_examples": [
            {"lang": "en", "q": "Show dark web contraband cases with a cross-border scope"},
            {"lang": "kn", "q": "ಗಡಿಯಾಚೆಗಿನ ಡಾರ್ಕ್‌ವೆಬ್ ಕಳ್ಳಸಾಗಣೆ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ"},
        ],
    },
    {
        "scenario_id": "P20-DARKWEB-002",
        "title": "Stolen-card data trade referencing a dark-web forum (manually classified)",
        "crime_family": "darkweb_fraud", "crime_subtype": "Dark Web Fraud",
        "jurisdiction_scope": "inter_state", "gravity": "Serious",
        "source_classification": "manual", "live_collection": False,
        "summary": ("Synthetic: a complaint describes stolen card data allegedly traded "
                    "on a dark-web forum, with buyers in another state. Manually "
                    "classified; no illegal-content collection is performed."),
        "districts": ["Bengaluru City"],
        "entities": [
            _n("p_buyer_d2", "person", "Synthetic buyer"),
            _n("src_d2", "source_record", "SYN-SRC-DARKWEB-0002", classification="manual", live_collection=False),
            _n("dev_d2", "device", "SYN-DEVICE-IMEI-0022"),
            _n("c_d2", "case", "SYN-FIR-DARKWEB-002"),
        ],
        "edges": [
            _e("src_d2", "manually_classified_as", "c_d2", "evidence-backed"),
            _e("p_buyer_d2", "used", "dev_d2", "hypothetical"),
        ],
        "referral": {"from": "state_police", "to": "other_state_cyber_cell (synthetic)", "kind": "inter_state_coordination"},
        "nl_examples": [
            {"lang": "en", "q": "List dark web fraud cases coordinated inter-state"},
            {"lang": "kn", "q": "ಅಂತರ-ರಾಜ್ಯ ಸಮನ್ವಯದ ಡಾರ್ಕ್‌ವೆಬ್ ವಂಚನೆ ಪ್ರಕರಣಗಳನ್ನು ಪಟ್ಟಿ ಮಾಡಿ"},
        ],
    },
    {
        "scenario_id": "P20-XJUR-001",
        "title": "Inter-district two-wheeler theft ring",
        "crime_family": "cross_jurisdiction", "crime_subtype": "Vehicle Theft",
        "jurisdiction_scope": "inter_district", "gravity": "Serious",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: a ring lifts two-wheelers in one district and re-sells "
                    "them in adjacent districts using tampered plates."),
        "districts": ["Bengaluru City", "Ramanagara", "Mandya"],
        "entities": [
            _n("p_ring1", "person", "Synthetic ring leader"),
            _n("veh1", "vehicle", "SYN-VEH-KA01-0001"),
            _n("veh2", "vehicle", "SYN-VEH-KA09-0002"),
            _n("loc_x1", "location", "Ramanagara"),
            _n("c_x1", "case", "SYN-FIR-XJUR-001"),
        ],
        "edges": [
            _e("p_ring1", "linked_to", "veh1", "evidence-backed", "recovered vehicle"),
            _e("p_ring1", "linked_to", "veh2", "hypothetical", "suspected, not recovered"),
            _e("c_x1", "resold_in", "loc_x1", "hypothetical"),
        ],
        "referral": {"from": "district_a", "to": "district_b", "kind": "inter_district_transfer"},
        "nl_examples": [
            {"lang": "en", "q": "Show inter-district vehicle theft rings"},
            {"lang": "kn", "q": "ಅಂತರ-ಜಿಲ್ಲಾ ವಾಹನ ಕಳ್ಳತನ ಜಾಲಗಳನ್ನು ತೋರಿಸಿ"},
        ],
    },
    {
        "scenario_id": "P20-XJUR-002",
        "title": "Inter-state cyber-fraud call centre",
        "crime_family": "cross_jurisdiction", "crime_subtype": "Cyber Fraud",
        "jurisdiction_scope": "inter_state", "gravity": "Serious",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: a call centre operating from another state defrauds "
                    "Karnataka victims; requires inter-state coordination."),
        "districts": ["Bengaluru City", "Dharwad"],
        "entities": [
            _n("p_cc2", "person", "Synthetic operator"),
            _n("ph_cc2", "phone", "SYN-PHONE-900000052"),
            _n("acct_cc2", "exchange_account", "SYN-BANK-ACC-0052"),
            _n("c_x2", "case", "SYN-FIR-XJUR-002"),
        ],
        "edges": [
            _e("p_cc2", "operated_via", "ph_cc2", "evidence-backed"),
            _e("acct_cc2", "received_proceeds", "c_x2", "evidence-backed"),
        ],
        "referral": {"from": "state_police", "to": "other_state_police (synthetic)", "kind": "inter_state_coordination"},
        "nl_examples": [
            {"lang": "en", "q": "Show vehicle thefts in Bengaluru South during the last 30 days"},
            {"lang": "kn", "q": "ಅಂತರ-ರಾಜ್ಯ ಸೈಬರ್ ವಂಚನೆ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ"},
        ],
    },
    {
        "scenario_id": "P20-XJUR-003",
        "title": "Cross-border trafficking referral",
        "crime_family": "cross_jurisdiction", "crime_subtype": "Human Trafficking",
        "jurisdiction_scope": "cross_border", "gravity": "Heinous",
        "source_classification": "reported_fir", "live_collection": False,
        "summary": ("Synthetic: a trafficking route crosses a national border; flagged "
                    "for central-agency and international coordination."),
        "districts": ["Belagavi"],
        "entities": [
            _n("p_traf3", "person", "Synthetic accused"),
            _n("loc_b3", "location", "Belagavi (border)"),
            _n("veh_b3", "vehicle", "SYN-VEH-KA22-0003"),
            _n("c_x3", "case", "SYN-FIR-XJUR-003"),
        ],
        "edges": [
            _e("p_traf3", "used", "veh_b3", "evidence-backed"),
            _e("c_x3", "crossed_at", "loc_b3", "hypothetical"),
        ],
        "referral": {"from": "state_police", "to": "Interpol/central-agency (synthetic)", "kind": "international_referral"},
        "nl_examples": [
            {"lang": "en", "q": "List cross-border trafficking cases needing international referral"},
            {"lang": "kn", "q": "ಅಂತರರಾಷ್ಟ್ರೀಯ ಉಲ್ಲೇಖ ಅಗತ್ಯವಿರುವ ಗಡಿಯಾಚೆಗಿನ ಕಳ್ಳಸಾಗಣೆ ಪ್ರಕರಣಗಳನ್ನು ಪಟ್ಟಿ ಮಾಡಿ"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Access + search
# ---------------------------------------------------------------------------
def scenario_count() -> int:
    return len(SCENARIOS)


def families_covered() -> set[str]:
    return {s["crime_family"] for s in SCENARIOS}


def scopes_covered() -> set[str]:
    return {s["jurisdiction_scope"] for s in SCENARIOS}


def _matches(scn: dict, query: Optional[str]) -> bool:
    if not query:
        return True
    q = query.strip().lower()
    hay = " ".join([
        scn["title"], scn["summary"], scn["crime_subtype"], scn["crime_family"],
        scn["jurisdiction_scope"], " ".join(scn.get("districts", [])),
        " ".join(ex["q"] for ex in scn.get("nl_examples", [])),
        CRIME_FAMILIES.get(scn["crime_family"], {}).get("kn", ""),
        CRIME_FAMILIES.get(scn["crime_family"], {}).get("label", ""),
    ]).lower()
    return q in hay


def search(query: Optional[str] = None, *, jurisdiction_scope: Optional[str] = None,
           crime_family: Optional[str] = None, limit: int = 50) -> list[dict]:
    out = []
    for scn in SCENARIOS:
        if jurisdiction_scope and scn["jurisdiction_scope"] != jurisdiction_scope:
            continue
        if crime_family and scn["crime_family"] != crime_family:
            continue
        if not _matches(scn, query):
            continue
        out.append(scn)
        if len(out) >= limit:
            break
    return out


def nl_examples() -> list[dict]:
    """Flattened NL-query examples (EN + KN) across all scenarios."""
    out = []
    for scn in SCENARIOS:
        for ex in scn.get("nl_examples", []):
            out.append({"scenario_id": scn["scenario_id"], "lang": ex["lang"],
                        "q": ex["q"], "crime_family": scn["crime_family"],
                        "jurisdiction_scope": scn["jurisdiction_scope"]})
    return out


# ---------------------------------------------------------------------------
# Validation gate (Prompt 20 Part A) — deterministic, offline
# ---------------------------------------------------------------------------
def validate() -> dict:
    """Integrity gates over the registry. Returns {ok, failures[], counts}."""
    failures: list[str] = []
    seen_ids: set[str] = set()

    for scn in SCENARIOS:
        sid = scn.get("scenario_id", "?")
        if sid in seen_ids:
            failures.append(f"{sid}: duplicate scenario_id")
        seen_ids.add(sid)
        # synthetic + no live collection
        if scn.get("live_collection") is not False:
            failures.append(f"{sid}: live_collection must be False")
        if scn.get("jurisdiction_scope") not in JURISDICTION_SCOPES:
            failures.append(f"{sid}: invalid jurisdiction_scope {scn.get('jurisdiction_scope')!r}")
        if scn.get("crime_family") not in CRIME_FAMILIES:
            failures.append(f"{sid}: invalid crime_family {scn.get('crime_family')!r}")
        # dark-web scenarios must be a manually classified source
        if scn["crime_family"].startswith("darkweb") and scn.get("source_classification") != "manual":
            failures.append(f"{sid}: dark-web scenario must be manually classified")
        # typed nodes + edges
        node_ids = {n["id"] for n in scn.get("entities", [])}
        for n in scn.get("entities", []):
            if n["type"] not in ENTITY_TYPES:
                failures.append(f"{sid}: node {n['id']} invalid type {n['type']!r}")
        if not scn.get("entities"):
            failures.append(f"{sid}: no entities")
        edges = scn.get("edges", [])
        if not edges:
            failures.append(f"{sid}: no edges")
        for e in edges:
            if e["basis"] not in EDGE_BASES:
                failures.append(f"{sid}: edge basis {e['basis']!r} invalid")
            if e["source"] not in node_ids or e["target"] not in node_ids:
                failures.append(f"{sid}: edge {e['source']}->{e['target']} references unknown node")
        # every dark-web scenario must carry a source_record node
        if scn["crime_family"].startswith("darkweb"):
            if not any(n["type"] == "source_record" for n in scn.get("entities", [])):
                failures.append(f"{sid}: dark-web scenario missing a source_record node")
        # every scenario must reference at least one case node
        if not any(n["type"] == "case" for n in scn.get("entities", [])):
            failures.append(f"{sid}: no case node")

    # coverage: all governed scopes + all crime families represented
    missing_scopes = set(JURISDICTION_SCOPES) - scopes_covered()
    if missing_scopes:
        failures.append(f"jurisdiction scopes not covered: {sorted(missing_scopes)}")
    missing_families = set(CRIME_FAMILIES) - families_covered()
    if missing_families:
        failures.append(f"crime families not covered: {sorted(missing_families)}")
    # crypto + dark-web presence
    if not any(s["crime_family"].startswith("crypto") for s in SCENARIOS):
        failures.append("no cryptocurrency scenario present")
    if not any(s["crime_family"].startswith("darkweb") for s in SCENARIOS):
        failures.append("no dark-web scenario present")

    return {
        "ok": not failures,
        "failures": failures,
        "counts": {
            "scenarios": len(SCENARIOS),
            "crypto": sum(1 for s in SCENARIOS if s["crime_family"].startswith("crypto")),
            "darkweb": sum(1 for s in SCENARIOS if s["crime_family"].startswith("darkweb")),
            "cross_jurisdiction": sum(1 for s in SCENARIOS if s["jurisdiction_scope"] != "local"),
            "jurisdiction_scopes": len(scopes_covered()),
            "crime_families": len(families_covered()),
            "nl_examples": len(nl_examples()),
            "edges_total": sum(len(s.get("edges", [])) for s in SCENARIOS),
            "hypothetical_edges": sum(1 for s in SCENARIOS for e in s.get("edges", [])
                                      if e["basis"] == "hypothetical"),
        },
    }
