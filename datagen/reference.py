"""Static domain knowledge for Karnataka: geography, crime taxonomy with
criminological behaviour profiles, legal acts/sections, org hierarchy, lookups
and name pools.

This module contains no randomness; it is the deterministic "world model" the
generator samples from.
"""
from __future__ import annotations

import math
from typing import Dict, List


# ---------------------------------------------------------------------------
# Hour-of-day weight templates (length 24). Built as sums of raised-cosine
# bumps around peak hours so distributions are smooth and realistic.
# ---------------------------------------------------------------------------
def _bumps(peaks, base=0.15, spread=3.0):
    w = [base] * 24
    for h in range(24):
        for pk, amp in peaks:
            d = min((h - pk) % 24, (pk - h) % 24)
            w[h] += amp * math.exp(-(d * d) / (2 * spread * spread))
    return w


HOUR_TEMPLATES = {
    "night":     _bumps([(23, 1.0), (1, 1.0), (3, 0.7)]),          # murder, burglary
    "late_night":_bumps([(1, 1.0), (2, 0.9), (23, 0.6)]),          # drunk driving, assault
    "afternoon": _bumps([(14, 1.0), (16, 0.8)]),                   # theft, pickpocket
    "evening":   _bumps([(19, 1.0), (21, 0.8)]),                   # robbery, molestation
    "morning":   _bumps([(9, 1.0), (11, 0.7)]),                    # cheating, forgery
    "business":  _bumps([(11, 0.9), (15, 0.9)]),                   # cyber, economic
    "allday":    [1.0] * 24,
}

# Weekday weight templates (Mon=0 .. Sun=6)
WEEKDAY_TEMPLATES = {
    "weekend":  [0.8, 0.8, 0.9, 1.0, 1.4, 1.9, 1.7],   # Fri/Sat/Sun spike
    "friday":   [0.9, 0.9, 1.0, 1.1, 1.6, 1.3, 1.0],
    "weekday":  [1.2, 1.2, 1.1, 1.1, 1.0, 0.7, 0.6],   # economic/cyber (working days)
    "uniform":  [1.0] * 7,
}

# Month weight templates (Jan=1 .. Dec=12), index 0 unused.
MONTH_TEMPLATES = {
    "festival":     [0, .8, .8, .9, .9, .8, .8, .9, 1.2, 1.5, 1.6, 1.3, 1.4],  # Dussehra/Deepavali/year-end
    "monsoon_low":  [0, 1.2, 1.2, 1.1, 1.0, .9, .7, .6, .6, .8, 1.0, 1.1, 1.2],  # Jun-Sep dip
    "summer":       [0, .9, 1.0, 1.2, 1.5, 1.6, 1.2, .9, .8, .9, 1.0, 1.0, .9],  # burglary in holidays
    "election":     [0, 1.0, 1.3, 1.6, 1.7, 1.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 1.0],
    "uniform":      [0] + [1.0] * 12,
}


# ---------------------------------------------------------------------------
# Karnataka districts (police-district granularity). Approx WGS84 centroids,
# behavioural tags and relative population weights.
#   tags drive crime affinity; pop_weight drives FIR + station allocation.
# ---------------------------------------------------------------------------
# (name, lat, lon, tags, pop_weight)
KARNATAKA_DISTRICTS = [
    ("Bengaluru City",      12.9716, 77.5946, ["metro", "urban"],            9.0),
    ("Bengaluru Urban",     13.0300, 77.5700, ["metro", "urban"],            4.5),
    ("Bengaluru Rural",     13.2200, 77.5700, ["rural", "periurban"],        1.4),
    ("Mysuru",              12.2958, 76.6394, ["urban"],                     3.0),
    ("Belagavi",            15.8497, 74.4977, ["urban", "border"],           3.2),
    ("Kalaburagi",          17.3297, 76.8343, ["urban", "border"],          2.4),
    ("Dakshina Kannada",    12.8703, 74.8806, ["coastal", "urban"],          2.6),
    ("Udupi",               13.3409, 74.7421, ["coastal"],                   1.3),
    ("Uttara Kannada",      14.8000, 74.1300, ["coastal", "rural"],          1.2),
    ("Ballari",             15.1394, 76.9214, ["urban", "mining"],           2.0),
    ("Vijayapura",          16.8302, 75.7100, ["rural", "border"],           1.8),
    ("Bidar",               17.9104, 77.5199, ["border", "rural"],           1.4),
    ("Raichur",             16.2076, 77.3463, ["rural", "border"],           1.6),
    ("Yadgir",              16.7700, 77.1376, ["rural", "border"],           1.0),
    ("Koppal",              15.3500, 76.1500, ["rural"],                     1.1),
    ("Davanagere",          14.4644, 75.9218, ["urban"],                     1.7),
    ("Dharwad",             15.4589, 75.0078, ["urban"],                     2.3),
    ("Gadag",               15.4315, 75.6355, ["rural"],                     0.9),
    ("Haveri",              14.7935, 75.4045, ["rural"],                     1.0),
    ("Shivamogga",          13.9299, 75.5681, ["urban", "rural"],            1.6),
    ("Chitradurga",         14.2306, 76.3985, ["rural"],                     1.2),
    ("Tumakuru",            13.3379, 77.1173, ["urban", "periurban"],        1.9),
    ("Hassan",              13.0068, 76.0996, ["rural"],                     1.3),
    ("Mandya",              12.5223, 76.8954, ["rural", "periurban"],        1.4),
    ("Chikkamagaluru",      13.3161, 75.7720, ["rural", "hilly"],            1.0),
    ("Kodagu",              12.4218, 75.7400, ["hilly", "rural"],            0.6),
    ("Chamarajanagar",      11.9236, 76.9456, ["border", "rural", "forest"], 0.8),
    ("Kolar",               13.1367, 78.1292, ["border", "rural"],           1.1),
    ("Chikkaballapur",      13.4355, 77.7315, ["border", "periurban"],       1.0),
    ("Ramanagara",          12.7217, 77.2807, ["periurban", "rural"],        0.9),
    ("Bagalkot",            16.1809, 75.6961, ["rural"],                     1.1),
    ("Vijayanagara",        15.2730, 76.4600, ["rural", "mining"],           0.9),
]


# ---------------------------------------------------------------------------
# Legal acts and (namespaced, globally-unique) sections.
#   Section codes are namespaced "ACT-nnn" because Section.SectionCode is the
#   primary key (unique across all acts) in the schema.
# ---------------------------------------------------------------------------
ACTS = [
    ("IPC",    "Indian Penal Code, 1860",                 "IPC"),
    ("ITACT",  "Information Technology Act, 2000",         "IT Act"),
    ("NDPS",   "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS Act"),
    ("MVACT",  "Motor Vehicles Act, 1988",                 "MV Act"),
    ("ARMS",   "Arms Act, 1959",                           "Arms Act"),
    ("DPACT",  "Dowry Prohibition Act, 1961",              "DP Act"),
    ("EXCISE", "Karnataka Excise Act, 1965",               "Excise Act"),
    ("POCSO",  "Protection of Children from Sexual Offences Act, 2012", "POCSO"),
]

# actcode -> list of (section_number, description)
_SECTIONS = {
    "IPC": [
        ("302", "Punishment for murder"),
        ("307", "Attempt to murder"),
        ("304", "Culpable homicide not amounting to murder"),
        ("304A", "Causing death by negligence"),
        ("323", "Voluntarily causing hurt"),
        ("324", "Voluntarily causing hurt by dangerous weapons"),
        ("325", "Voluntarily causing grievous hurt"),
        ("354", "Assault on woman with intent to outrage modesty"),
        ("363", "Punishment for kidnapping"),
        ("364", "Kidnapping in order to murder"),
        ("366", "Kidnapping/abducting woman to compel marriage"),
        ("370", "Trafficking of persons"),
        ("376", "Punishment for rape"),
        ("379", "Punishment for theft"),
        ("380", "Theft in dwelling house"),
        ("392", "Punishment for robbery"),
        ("395", "Punishment for dacoity"),
        ("420", "Cheating and dishonestly inducing delivery of property"),
        ("457", "Lurking house-trespass or house-breaking by night"),
        ("468", "Forgery for purpose of cheating"),
        ("471", "Using as genuine a forged document"),
        ("498A", "Husband or relative subjecting woman to cruelty"),
        ("120B", "Punishment of criminal conspiracy"),
        ("201", "Causing disappearance of evidence or giving false information to screen an offender"),
        ("355", "Assault or criminal force with intent to dishonour a person"),
        ("384", "Punishment for extortion"),
        ("143", "Punishment for being member of unlawful assembly"),
        ("147", "Punishment for rioting"),
        ("148", "Rioting, armed with deadly weapon"),
        ("149", "Offence committed by a member of an unlawful assembly in prosecution of common object"),
        ("34", "Acts done by several persons in furtherance of common intention"),
        ("506", "Punishment for criminal intimidation"),
    ],
    "ITACT": [
        ("66", "Computer related offences"),
        ("66C", "Punishment for identity theft"),
        ("66D", "Cheating by personation using computer resource"),
        ("43", "Penalty for damage to computer system"),
    ],
    "NDPS": [
        ("20", "Contravention in relation to cannabis"),
        ("21", "Contravention in relation to manufactured drugs"),
        ("22", "Contravention in relation to psychotropic substances"),
        ("8C", "Prohibition of certain operations"),
    ],
    "MVACT": [
        ("184", "Driving dangerously"),
        ("185", "Driving by a drunken person"),
        ("134", "Duty of driver in case of accident"),
    ],
    "ARMS": [
        ("25", "Punishment for certain offences (Arms)"),
        ("27", "Punishment for using arms"),
    ],
    "DPACT": [
        ("3", "Penalty for giving or taking dowry"),
        ("4", "Penalty for demanding dowry"),
    ],
    "EXCISE": [
        ("32", "Unlawful possession of liquor"),
        ("34", "Illegal transport of liquor"),
    ],
    "POCSO": [
        ("4", "Punishment for penetrative sexual assault"),
        ("8", "Punishment for sexual assault"),
    ],
}


def section_code(act: str, num: str) -> str:
    return f"{act}-{num}"


def all_sections():
    """Yield (section_code, act_code, description)."""
    for act, secs in _SECTIONS.items():
        for num, desc in secs:
            yield section_code(act, num), act, desc


# ---------------------------------------------------------------------------
# Crime taxonomy with behavioural profiles.
#   `weight` gives the (Zipf-like) relative frequency of each crime type.
#   `affinity` multiplies weight for districts carrying the given tag.
# ---------------------------------------------------------------------------
def _p(head, sub, weight, gravity, hours, weekday, season, urban_bias,
       affinity, accused_mean, victims_mean, age, repeat, arrest,
       known_accused, gang, alcohol, multi_victim, acts):
    return dict(head=head, sub=sub, weight=weight, gravity=gravity, hours=hours,
                weekday=weekday, season=season, urban_bias=urban_bias,
                affinity=affinity, accused_mean=accused_mean,
                victims_mean=victims_mean, age=age, repeat=repeat, arrest=arrest,
                known_accused=known_accused, gang=gang, alcohol=alcohol,
                multi_victim=multi_victim, acts=acts)


CRIME_PROFILES: List[dict] = [
    # --- Crimes Against Body -------------------------------------------------
    _p("Crimes Against Body", "Murder", 2.0, "Heinous", "night", "weekend",
       "uniform", 0.35, {"rural": 1.4, "border": 1.1},
       accused_mean=1.6, victims_mean=1.1, age=(32, 10), repeat=0.20, arrest=0.82,
       known_accused=0.72, gang=0.12, alcohol=0.55, multi_victim=False,
       acts=[("IPC", ["302"]), ("ARMS", ["25"])]),
    _p("Crimes Against Body", "Attempt to Murder", 2.4, "Heinous", "night",
       "weekend", "uniform", 0.45, {"urban": 1.2},
       accused_mean=2.0, victims_mean=1.2, age=(30, 9), repeat=0.28, arrest=0.7,
       known_accused=0.6, gang=0.18, alcohol=0.5, multi_victim=False,
       acts=[("IPC", ["307"]), ("ARMS", ["25"])]),
    _p("Crimes Against Body", "Grievous Hurt", 4.5, "Serious", "evening",
       "weekend", "uniform", 0.5, {"urban": 1.1},
       accused_mean=2.2, victims_mean=1.3, age=(28, 9), repeat=0.3, arrest=0.62,
       known_accused=0.55, gang=0.15, alcohol=0.6, multi_victim=False,
       acts=[("IPC", ["325", "324"])]),
    _p("Crimes Against Body", "Assault", 8.0, "Non-Heinous", "late_night",
       "friday", "uniform", 0.55, {"urban": 1.2},
       accused_mean=2.4, victims_mean=1.2, age=(26, 8), repeat=0.35, arrest=0.5,
       known_accused=0.5, gang=0.12, alcohol=0.65, multi_victim=False,
       acts=[("IPC", ["323", "506"])]),
    _p("Crimes Against Body", "Kidnapping", 1.6, "Heinous", "evening", "uniform",
       "uniform", 0.5, {"urban": 1.1, "border": 1.2},
       accused_mean=2.6, victims_mean=1.1, age=(29, 8), repeat=0.22, arrest=0.55,
       known_accused=0.45, gang=0.3, alcohol=0.15, multi_victim=False,
       acts=[("IPC", ["363", "364"])]),
    _p("Crimes Against Body", "Human Trafficking", 0.5, "Heinous", "night",
       "uniform", "uniform", 0.6, {"border": 1.6, "coastal": 1.3, "metro": 1.4},
       accused_mean=3.5, victims_mean=4.0, age=(33, 9), repeat=0.4, arrest=0.4,
       known_accused=0.3, gang=0.7, alcohol=0.05, multi_victim=True,
       acts=[("IPC", ["370", "366"])]),

    # --- Crimes Against Property --------------------------------------------
    _p("Crimes Against Property", "Theft", 16.0, "Non-Heinous", "afternoon",
       "uniform", "festival", 0.7, {"metro": 1.5, "urban": 1.3},
       accused_mean=1.5, victims_mean=1.0, age=(27, 8), repeat=0.45, arrest=0.28,
       known_accused=0.18, gang=0.1, alcohol=0.1, multi_victim=False,
       acts=[("IPC", ["379"])]),
    _p("Crimes Against Property", "Burglary", 6.0, "Serious", "night", "uniform",
       "summer", 0.55, {"urban": 1.2, "metro": 1.3},
       accused_mean=2.0, victims_mean=1.0, age=(29, 8), repeat=0.55, arrest=0.32,
       known_accused=0.12, gang=0.25, alcohol=0.1, multi_victim=False,
       acts=[("IPC", ["457", "380"])]),
    _p("Crimes Against Property", "Robbery", 4.0, "Heinous", "evening",
       "weekend", "festival", 0.72, {"metro": 1.6, "urban": 1.3},
       accused_mean=2.6, victims_mean=1.2, age=(26, 7), repeat=0.5, arrest=0.4,
       known_accused=0.15, gang=0.35, alcohol=0.2, multi_victim=False,
       acts=[("IPC", ["392"]), ("ARMS", ["25"])]),
    _p("Crimes Against Property", "Dacoity", 0.6, "Heinous", "night", "uniform",
       "uniform", 0.4, {"rural": 1.3, "border": 1.2},
       accused_mean=5.5, victims_mean=1.5, age=(30, 8), repeat=0.5, arrest=0.45,
       known_accused=0.12, gang=0.8, alcohol=0.2, multi_victim=False,
       acts=[("IPC", ["395"]), ("ARMS", ["25", "27"])]),
    _p("Crimes Against Property", "Vehicle Theft", 7.0, "Non-Heinous", "night",
       "uniform", "uniform", 0.75, {"metro": 1.7, "urban": 1.3},
       accused_mean=1.8, victims_mean=1.0, age=(25, 7), repeat=0.6, arrest=0.22,
       known_accused=0.08, gang=0.3, alcohol=0.1, multi_victim=False,
       acts=[("IPC", ["379"])]),

    # --- Crimes Against Women ------------------------------------------------
    _p("Crimes Against Women", "Molestation", 3.5, "Serious", "evening",
       "uniform", "festival", 0.6, {"urban": 1.2, "metro": 1.2},
       accused_mean=1.4, victims_mean=1.0, age=(29, 9), repeat=0.25, arrest=0.6,
       known_accused=0.55, gang=0.05, alcohol=0.35, multi_victim=False,
       acts=[("IPC", ["354"])]),
    _p("Crimes Against Women", "Rape", 1.5, "Heinous", "night", "uniform",
       "uniform", 0.45, {"urban": 1.1},
       accused_mean=1.3, victims_mean=1.0, age=(30, 9), repeat=0.15, arrest=0.78,
       known_accused=0.82, gang=0.06, alcohol=0.3, multi_victim=False,
       acts=[("IPC", ["376"]), ("POCSO", ["4"])]),
    _p("Crimes Against Women", "Dowry Harassment", 3.0, "Serious", "allday",
       "uniform", "uniform", 0.45, {"rural": 1.2, "urban": 1.0},
       accused_mean=3.2, victims_mean=1.0, age=(34, 8), repeat=0.05, arrest=0.5,
       known_accused=1.0, gang=0.0, alcohol=0.2, multi_victim=False,
       acts=[("IPC", ["498A"]), ("DPACT", ["3", "4"])]),

    # --- Economic / Cyber ----------------------------------------------------
    _p("Economic & Cyber Crime", "Cyber Fraud", 6.5, "Serious", "business",
       "weekday", "uniform", 0.9, {"metro": 2.0, "urban": 1.4},
       accused_mean=2.2, victims_mean=3.5, age=(24, 5), repeat=0.4, arrest=0.18,
       known_accused=0.05, gang=0.45, alcohol=0.02, multi_victim=True,
       acts=[("ITACT", ["66D", "66C"]), ("IPC", ["420"])]),
    _p("Economic & Cyber Crime", "OTP Scam", 4.5, "Non-Heinous", "business",
       "weekday", "uniform", 0.92, {"metro": 2.1, "urban": 1.4},
       accused_mean=2.5, victims_mean=5.0, age=(23, 4), repeat=0.5, arrest=0.12,
       known_accused=0.03, gang=0.5, alcohol=0.02, multi_victim=True,
       acts=[("ITACT", ["66D"]), ("IPC", ["420"])]),
    _p("Economic & Cyber Crime", "Bank Fraud", 2.5, "Serious", "business",
       "weekday", "uniform", 0.85, {"metro": 1.8, "urban": 1.3},
       accused_mean=2.0, victims_mean=2.0, age=(31, 7), repeat=0.3, arrest=0.25,
       known_accused=0.2, gang=0.35, alcohol=0.02, multi_victim=True,
       acts=[("IPC", ["420", "468", "471"]), ("ITACT", ["66"])]),
    _p("Economic & Cyber Crime", "Cheating", 5.0, "Non-Heinous", "morning",
       "weekday", "uniform", 0.7, {"urban": 1.2},
       accused_mean=1.8, victims_mean=1.4, age=(35, 9), repeat=0.25, arrest=0.35,
       known_accused=0.45, gang=0.1, alcohol=0.02, multi_victim=False,
       acts=[("IPC", ["420"])]),
    # --- Prompt 20 §A: cryptocurrency- / dark-web-enabled (clearly synthetic) --
    # Low weights; additive so a future full regen also carries these subheads.
    # Dark-web is a MANUALLY classified source only (no scraping/purchase/creds).
    _p("Economic & Cyber Crime", "Cryptocurrency Fraud", 1.2, "Serious", "business",
       "weekday", "uniform", 0.92, {"metro": 2.1, "urban": 1.4},
       accused_mean=2.2, victims_mean=3.0, age=(27, 6), repeat=0.4, arrest=0.14,
       known_accused=0.04, gang=0.4, alcohol=0.02, multi_victim=True,
       acts=[("ITACT", ["66D", "66C"]), ("IPC", ["420"])]),
    _p("Economic & Cyber Crime", "Crypto Extortion", 0.5, "Serious", "business",
       "uniform", "uniform", 0.9, {"metro": 1.9, "urban": 1.3},
       accused_mean=1.6, victims_mean=1.2, age=(28, 7), repeat=0.35, arrest=0.16,
       known_accused=0.05, gang=0.3, alcohol=0.02, multi_victim=False,
       acts=[("ITACT", ["66D"]), ("IPC", ["506", "420"])]),
    _p("Economic & Cyber Crime", "Dark Web Crime", 0.4, "Heinous", "business",
       "uniform", "uniform", 0.9, {"metro": 1.8, "border": 1.3},
       accused_mean=2.0, victims_mean=1.5, age=(29, 7), repeat=0.45, arrest=0.10,
       known_accused=0.03, gang=0.5, alcohol=0.02, multi_victim=True,
       acts=[("ITACT", ["66", "66C"]), ("NDPS", ["22"]), ("IPC", ["420"])]),

    # --- Drugs (NDPS) --------------------------------------------------------
    _p("Drug Offences", "Drug Peddling", 3.0, "Serious", "late_night", "uniform",
       "uniform", 0.7, {"border": 1.8, "coastal": 1.3, "metro": 1.4},
       accused_mean=1.6, victims_mean=0.0, age=(27, 7), repeat=0.55, arrest=0.9,
       known_accused=0.4, gang=0.35, alcohol=0.1, multi_victim=False,
       acts=[("NDPS", ["20", "21"])]),
    _p("Drug Offences", "Drug Trafficking", 1.4, "Heinous", "night", "uniform",
       "uniform", 0.5, {"border": 2.0, "coastal": 1.5},
       accused_mean=3.0, victims_mean=0.0, age=(31, 8), repeat=0.5, arrest=0.85,
       known_accused=0.3, gang=0.65, alcohol=0.05, multi_victim=False,
       acts=[("NDPS", ["21", "22", "8C"])]),

    # --- Public Order --------------------------------------------------------
    _p("Public Order", "Rioting", 2.0, "Serious", "evening", "uniform",
       "election", 0.6, {"urban": 1.2, "border": 1.1},
       accused_mean=8.0, victims_mean=1.5, age=(28, 9), repeat=0.2, arrest=0.45,
       known_accused=0.4, gang=0.25, alcohol=0.35, multi_victim=True,
       acts=[("IPC", ["143", "147", "148"])]),

    # --- Traffic -------------------------------------------------------------
    _p("Traffic Offences", "Drunk Driving", 5.0, "Non-Heinous", "late_night",
       "weekend", "uniform", 0.8, {"metro": 1.5, "urban": 1.3},
       accused_mean=1.0, victims_mean=0.0, age=(30, 9), repeat=0.35, arrest=0.95,
       known_accused=1.0, gang=0.0, alcohol=1.0, multi_victim=False,
       acts=[("MVACT", ["185"])]),
    _p("Traffic Offences", "Hit and Run", 2.2, "Serious", "night", "uniform",
       "uniform", 0.65, {"urban": 1.2, "metro": 1.2},
       accused_mean=1.0, victims_mean=1.3, age=(33, 10), repeat=0.1, arrest=0.4,
       known_accused=0.15, gang=0.0, alcohol=0.4, multi_victim=False,
       acts=[("MVACT", ["184", "134"]), ("IPC", ["304A"])]),

    # --- Smuggling -----------------------------------------------------------
    _p("Smuggling & Excise", "Smuggling", 1.2, "Serious", "night", "uniform",
       "uniform", 0.5, {"coastal": 2.0, "border": 1.6},
       accused_mean=2.8, victims_mean=0.0, age=(34, 9), repeat=0.45, arrest=0.7,
       known_accused=0.3, gang=0.6, alcohol=0.1, multi_victim=False,
       acts=[("EXCISE", ["34"]), ("IPC", ["420"])]),
    _p("Smuggling & Excise", "Illicit Liquor", 2.5, "Non-Heinous", "night",
       "uniform", "uniform", 0.45, {"border": 1.4, "rural": 1.2},
       accused_mean=1.8, victims_mean=0.0, age=(36, 10), repeat=0.5, arrest=0.85,
       known_accused=0.35, gang=0.3, alcohol=0.3, multi_victim=False,
       acts=[("EXCISE", ["32", "34"])]),

    # --- Missing / misc ------------------------------------------------------
    _p("Miscellaneous", "Missing Person", 3.0, "Non-Heinous", "allday",
       "uniform", "uniform", 0.6, {},
       accused_mean=0.0, victims_mean=1.0, age=(0, 0), repeat=0.0, arrest=0.05,
       known_accused=0.0, gang=0.0, alcohol=0.0, multi_victim=False,
       acts=[]),
]


# ---------------------------------------------------------------------------
# Organisational lookups
# ---------------------------------------------------------------------------
UNIT_TYPES = [
    ("Police Station", "District", 3),
    ("Circle Office", "District", 2),
    ("Sub-Division", "District", 2),
    ("District HQ", "District", 1),
    ("Commissionerate", "City", 1),
    ("State CID", "State", 0),
]

RANKS = [
    # (name, hierarchy)  lower hierarchy == higher rank
    ("Director General of Police", 1),
    ("Additional Director General", 2),
    ("Inspector General", 3),
    ("Deputy Inspector General", 4),
    ("Superintendent of Police", 5),
    ("Additional SP", 6),
    ("Deputy SP", 7),
    ("Police Inspector", 8),
    ("Police Sub-Inspector", 9),
    ("Assistant Sub-Inspector", 10),
    ("Head Constable", 11),
    ("Police Constable", 12),
]

# Weight of how many officers hold each rank (many constables, few senior).
RANK_STAFFING = [0.2, 0.4, 1, 2, 5, 8, 20, 60, 120, 200, 400, 900]

DESIGNATIONS = [
    ("Station House Officer", 1),
    ("Investigating Officer", 2),
    ("Circle Inspector", 3),
    ("Law & Order In-charge", 4),
    ("Crime Branch Officer", 5),
    ("Traffic Officer", 6),
    ("Cyber Cell Officer", 7),
    ("Reserve Officer", 8),
]

CASE_CATEGORIES = ["FIR", "UDR", "Zero FIR", "PAR", "NCR"]
CATEGORY_CODE = {"FIR": 1, "UDR": 3, "Zero FIR": 8, "PAR": 4, "NCR": 5}
CATEGORY_WEIGHTS = [0.82, 0.05, 0.03, 0.05, 0.05]

# Prompt 20 §A.2 — jurisdiction SCOPE is modelled SEPARATELY from crime type.
# Governed values (a case/scenario carries one), used by the additive
# crypto/dark-web/cross-jurisdiction scenario registry (services/ml/app/scenarios).
JURISDICTION_SCOPES = [
    "local", "inter_district", "inter_state", "national", "international", "cross_border",
]

GRAVITY_LEVELS = ["Heinous", "Serious", "Non-Heinous"]

CASE_STATUSES = [
    "Under Investigation", "Charge Sheeted", "Closed - Convicted",
    "Closed - Acquitted", "Undetected / B-Report", "False / C-Report",
    "Pending Trial", "Transferred",
    # --- Datagen v2 lifecycle statuses (appended; legacy indices unchanged) ---
    # Needed so category-specific lifecycles (missing person / UDR / NCR / PAR)
    # map to an FK-valid CaseStatusMaster row instead of being forced into a
    # cognizable-FIR status. See datagen/scenario_registry.py:EXTRA_STATUS_NAMES.
    "Missing - Under Trace", "Missing - Recovered", "Closed - Untraced",
    "Enquiry Closed", "Inquest Closed", "Converted / Reclassified",
]

RELIGIONS = ["Hindu", "Muslim", "Christian", "Jain", "Sikh", "Buddhist", "Other"]
RELIGION_WEIGHTS = [0.82, 0.11, 0.03, 0.015, 0.008, 0.007, 0.01]

CASTES = [
    "General", "OBC", "SC", "ST", "Lingayat", "Vokkaliga", "Brahmin",
    "Kuruba", "Other Backward", "Not Disclosed",
]

OCCUPATIONS = [
    "Farmer", "Daily Wage Labourer", "Student", "Private Employee",
    "Government Employee", "Business/Trader", "Driver", "Unemployed",
    "Homemaker", "Skilled Worker", "IT Professional", "Auto/Cab Driver",
    "Shopkeeper", "Agricultural Labourer", "Self-Employed",
]

# GenderID lookup values used across person tables (1=Male, 2=Female, 3=Trans)
GENDER_MALE, GENDER_FEMALE, GENDER_TRANS = 1, 2, 3
BLOOD_GROUPS = list(range(1, 9))  # 1..8 -> A+,A-,B+,B-,O+,O-,AB+,AB-


# ---------------------------------------------------------------------------
# Name pools (Karnataka / South-Indian leaning)
# ---------------------------------------------------------------------------
MALE_NAMES = [
    "Ravi", "Suresh", "Manjunath", "Prakash", "Ramesh", "Naveen", "Kiran",
    "Anand", "Basavaraj", "Shivakumar", "Mahesh", "Nagaraj", "Vijay", "Santosh",
    "Girish", "Umesh", "Harish", "Ganesh", "Chandan", "Darshan", "Rakesh",
    "Vinay", "Praveen", "Lokesh", "Sandeep", "Arun", "Deepak", "Yogesh",
    "Mohammed", "Imran", "Faizal", "Riyaz", "Abdul", "Syed", "Ibrahim",
    "Venkatesh", "Srinivas", "Gopal", "Krishna", "Raju", "Madhu", "Bharath",
]
FEMALE_NAMES = [
    "Lakshmi", "Savitha", "Roopa", "Geetha", "Sunitha", "Manjula", "Pooja",
    "Deepa", "Kavya", "Ashwini", "Divya", "Shruthi", "Sowmya", "Rekha",
    "Nagaratna", "Chaitra", "Bhavya", "Ananya", "Meena", "Vidya", "Shweta",
    "Ayesha", "Fatima", "Nasreen", "Zoya", "Salma", "Ruksana",
    "Padma", "Radha", "Sridevi", "Anitha", "Vani", "Bhagya",
]
SURNAMES = [
    "Gowda", "Reddy", "Patil", "Naik", "Hegde", "Shetty", "Rao", "Bhat",
    "Kumar", "Murthy", "Prasad", "Setty", "Achar", "Kulkarni", "Desai",
    "Nayak", "Poojary", "Shenoy", "Iyer", "Gupta", "Khan", "Sheikh",
    "Ansari", "Pujar", "Angadi", "Hiremath", "Math", "Swamy", "Raj",
]

GANG_ADJ = ["Black", "Red", "Royal", "Silent", "Iron", "Shadow", "Golden",
            "Steel", "Night", "Cobra", "Tiger", "Falcon", "Rowdy"]
GANG_NOUN = ["Cobras", "Tigers", "Brothers", "Warriors", "Falcons", "Kings",
             "Riders", "Sharks", "Hunters", "Wolves", "Eagles", "Panthers",
             "Company", "Gang", "Boys"]

VEHICLE_TYPES = ["Motorcycle", "Car", "Auto-rickshaw", "Tempo", "Lorry", "SUV"]
KA_RTO = ["KA01", "KA02", "KA03", "KA04", "KA05", "KA09", "KA19", "KA20",
          "KA25", "KA28", "KA31", "KA36", "KA41", "KA51", "KA52", "KA53"]
