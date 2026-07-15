"""Curated EN/KN police & legal glossary (doc 02 §6, multilingual).

Generic translation mangles domain terms; injecting this glossary keeps FIR /
accused / MO / gravity correct when the question is in Kannada. Shown to the LLM
so the natural-language reply and any filter values map to the right columns.
"""
from __future__ import annotations

# (english, kannada, mapping hint for NL->SQL)
GLOSSARY: list[tuple[str, str, str]] = [
    ("FIR / crime", "ಎಫ್‌ಐಆರ್ / ಪ್ರಕರಣ", 'CaseMaster (a row = one FIR)'),
    ("accused", "ಆರೋಪಿ", '"Accused" table'),
    ("victim", "ಸಂತ್ರಸ್ತ", '"Victim" table'),
    ("complainant", "ದೂರುದಾರ", '"ComplainantDetails" table'),
    ("district", "ಜಿಲ್ಲೆ", '"District"."DistrictName"'),
    ("police station", "ಠಾಣೆ", '"Unit"."UnitName"'),
    ("theft", "ಕಳ್ಳತನ", 'CrimeSubHead.CrimeHeadName ILIKE \'%Theft%\''),
    ("robbery", "ದರೋಡೆ", 'CrimeSubHead ILIKE \'%Robbery%\''),
    ("murder", "ಕೊಲೆ", 'CrimeSubHead ILIKE \'%Murder%\''),
    ("cyber crime", "ಸೈಬರ್ ಅಪರಾಧ", 'CrimeHead.CrimeGroupName ILIKE \'%cyber%\''),
    ("vehicle theft", "ವಾಹನ ಕಳ್ಳತನ", 'CrimeSubHead ILIKE \'%Vehicle Theft%\''),
    ("heinous", "ಘೋರ", 'GravityOffence.LookupValue = \'Heinous\''),
    ("chargesheet", "ದೋಷಾರೋಪ ಪಟ್ಟಿ", '"ChargesheetDetails"'),
    ("arrest", "ಬಂಧನ", '"ArrestSurrender"'),
    ("under investigation", "ತನಿಖೆಯಲ್ಲಿ", 'CaseStatusMaster.CaseStatusName ILIKE \'%investigation%\''),
    ("modus operandi (MO)", "ಕಾರ್ಯವಿಧಾನ", 'CrimePattern (modus_operandi) / brief facts'),
    ("hotspot", "ಅಪರಾಧ ಕೇಂದ್ರ", '"CrimeHotspot"'),
    ("gang", "ಗ್ಯಾಂಗ್", 'EntityGraph (EntityType=gang) / GangMembership'),
    # --- more crime heads / sub-heads ---
    ("burglary / house-breaking", "ಮನೆಗಳ್ಳತನ", 'CrimeSubHead ILIKE \'%Burglar%\''),
    ("dacoity", "ಡಕಾಯಿತಿ", 'CrimeSubHead ILIKE \'%Dacoit%\''),
    ("assault / hurt", "ಹಲ್ಲೆ", 'CrimeSubHead ILIKE \'%Assault%\''),
    ("kidnapping / abduction", "ಅಪಹರಣ", 'CrimeSubHead ILIKE \'%Kidnap%\''),
    ("rape / sexual assault", "ಅತ್ಯಾಚಾರ", 'CrimeSubHead ILIKE \'%Rape%\''),
    ("cheating / fraud", "ವಂಚನೆ", 'CrimeSubHead ILIKE \'%Cheat%\''),
    ("narcotics / drugs", "ಮಾದಕ ದ್ರವ್ಯ", 'CrimeSubHead ILIKE \'%Narcotic%\''),
    ("missing person", "ನಾಪತ್ತೆ", 'CrimeSubHead ILIKE \'%Missing%\''),
    ("riot / unlawful assembly", "ಗಲಭೆ", 'CrimeSubHead ILIKE \'%Riot%\''),
    ("extortion", "ಸುಲಿಗೆ", 'CrimeSubHead ILIKE \'%Extortion%\''),
    # --- gravity / status ---
    ("serious", "ಗಂಭೀರ", 'GravityOffence.LookupValue = \'Serious\''),
    ("petty", "ಸಣ್ಣ", 'GravityOffence.LookupValue = \'Petty\''),
    ("disposed / closed", "ವಿಲೇವಾರಿ", 'CaseStatusMaster.CaseStatusName ILIKE \'%dispos%\''),
    # --- derived intelligence ---
    ("forecast / prediction", "ಮುನ್ಸೂಚನೆ", '"CrimePrediction"'),
    ("risk", "ಅಪಾಯ", '"CrimeRiskScore"'),
    # --- query verbs (help the LLM map intent) ---
    ("how many / count", "ಎಷ್ಟು / ಸಂಖ್ಯೆ", 'COUNT(*)'),
    ("list / show", "ತೋರಿಸಿ / ಪಟ್ಟಿ", 'SELECT rows (aggregate for policymaker)'),
    ("top / most", "ಅತಿ ಹೆಚ್ಚು / ಹೆಚ್ಚು", 'ORDER BY COUNT(*) DESC'),
    ("trend / over time", "ಪ್ರವೃತ್ತಿ", 'GROUP BY month'),
    ("recent / latest", "ಇತ್ತೀಚಿನ", 'ORDER BY date DESC'),
]


def glossary_text() -> str:
    rows = "\n".join(f"- {en}  =  {kn}  ->  {hint}" for en, kn, hint in GLOSSARY)
    return "POLICE/LEGAL GLOSSARY (English = ಕನ್ನಡ -> column):\n" + rows
