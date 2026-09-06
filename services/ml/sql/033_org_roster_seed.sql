-- DRISHTI migration 033: Wing and Range roster seed (supersedes the held draft).
--
-- Roster verified against the official source:
--   https://ksp.karnataka.gov.in/page/About+Us/Organization/en (retrieved 2026-09-05)
-- Official structure: 7 ranges headed by IGPs, each of 3 to 6 districts; districts
-- headed by SPs; 6 Police Commissionerates, the Bengaluru City CP at ADGP rank and
-- the other five at DIG rank. Content paraphrased for licensing compliance.
--
-- Range membership here covers only the districts that ALREADY exist as District
-- rows. The five city Commissionerates and KGF are created by migration 034,
-- which assigns their range membership (or deliberate absence) itself.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Six functional wings (ADGP command). State-wide; narrowed by crime head.
-- ---------------------------------------------------------------------------
INSERT INTO "Wing" ("WingName", "WingCode", "Description") VALUES
    ('Law & Order', 'LO',
     'Public order, communal and mob incidents, SC/ST case oversight.'),
    ('Crime & Technical Services', 'CTS',
     'State crime records, Finger Print Bureau, Forensic Science Laboratory, Police Computer Wing, SCRB. Absorbs the former crime_analyst seat.'),
    ('Intelligence', 'INT',
     'State Intelligence Wing; five divisions at Bengaluru, Mysuru, Mangaluru, Kalaburagi and Belagavi.'),
    ('Internal Security & Cyber', 'ISC',
     'Internal Security Division: Coastal Security, Anti Naxal Force, Anti Terrorist Cell, counter-terrorism, KSISF. Absorbs the former cyber_cell seat.'),
    ('Traffic & Road Safety', 'TRF',
     'Road-safety hotspots, accident patterns and enforcement load. Absorbs the former traffic_command seat.'),
    ('CID / Economic Offences', 'CID',
     'Criminal Investigation Department: Corps of Detectives, Forest Cell, Economic Offences unit, Cyber Police Station.')
ON CONFLICT ("WingCode") DO UPDATE
    SET "WingName" = EXCLUDED."WingName", "Description" = EXCLUDED."Description";

-- Crime heads per wing. Crime & Technical Services is deliberately absent:
-- it is accountable for every head, and "no rows" means "all heads".
INSERT INTO "WingCrimeHead" ("WingID", "CrimeHeadID")
SELECT w."WingID", ch."CrimeHeadID"
  FROM "Wing" w
  JOIN (VALUES
        ('LO','Public Order'), ('LO','Crimes Against Body'), ('LO','Crimes Against Women'),
        ('INT','Public Order'), ('INT','Crimes Against Body'), ('INT','Smuggling & Excise'),
        ('ISC','Economic & Cyber Crime'),
        ('TRF','Traffic Offences'),
        ('CID','Economic & Cyber Crime'), ('CID','Crimes Against Property'), ('CID','Drug Offences')
       ) AS v(wing_code, head_name) ON v.wing_code = w."WingCode"
  JOIN "CrimeHead" ch ON ch."CrimeGroupName" = v.head_name
ON CONFLICT ("WingID", "CrimeHeadID") DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Seven ranges (IGP command).
-- ---------------------------------------------------------------------------
INSERT INTO "Range" ("RangeName", "RangeCode", "StateID") VALUES
    ('Southern Range, Mysuru',          'SR',  1),
    ('Western Range, Mangaluru',        'WR',  1),
    ('Eastern Range, Davanagere',       'ER',  1),
    ('Central Range, Bengaluru',        'CR',  1),
    ('Northern Range, Belagavi',        'NR',  1),
    ('North Eastern Range, Kalaburagi', 'NER', 1),
    ('Ballari Range, Ballari',          'BR',  1)
ON CONFLICT ("RangeCode") DO UPDATE SET "RangeName" = EXCLUDED."RangeName";

UPDATE "Range" r SET "HQDistrictID" = d."DistrictID"
  FROM "District" d
 WHERE (r."RangeCode", d."DistrictName") IN
       (('SR','Mysuru'), ('WR','Dakshina Kannada'), ('ER','Davanagere'),
        ('CR','Bengaluru Urban'), ('NR','Belagavi'), ('NER','Kalaburagi'),
        ('BR','Ballari'));

-- ---------------------------------------------------------------------------
-- 3. Range membership for the districts that already exist.
--    Every one of these is a RURAL/district police unit under an SP. The city
--    Commissionerates carved out of Mysuru, Dakshina Kannada, Dharwad, Belagavi
--    and Kalaburagi are created separately in 034 — these rows keep the rural
--    remainder, which is what the official range table refers to.
-- ---------------------------------------------------------------------------
UPDATE "District" d
   SET "RangeID" = r."RangeID",
       "IsCommissionerate" = FALSE,
       "CommandRank" = 'SP'
  FROM "Range" r,
       (VALUES
        ('SR','Mysuru'), ('SR','Kodagu'), ('SR','Mandya'), ('SR','Hassan'),
        ('SR','Chamarajanagar'),
        ('WR','Dakshina Kannada'), ('WR','Uttara Kannada'), ('WR','Udupi'),
        ('WR','Chikkamagaluru'),
        ('ER','Chitradurga'), ('ER','Haveri'), ('ER','Shivamogga'), ('ER','Davanagere'),
        ('CR','Tumakuru'), ('CR','Kolar'), ('CR','Bengaluru Rural'),
        ('CR','Chikkaballapur'), ('CR','Ramanagara'), ('CR','Bengaluru Urban'),
        ('NR','Belagavi'), ('NR','Vijayapura'), ('NR','Dharwad'),
        ('NR','Bagalkot'), ('NR','Gadag'),
        ('NER','Kalaburagi'), ('NER','Bidar'), ('NER','Yadgir'),
        ('BR','Ballari'), ('BR','Vijayanagara'), ('BR','Raichur'), ('BR','Koppal')
       ) AS v(range_code, district_name)
 WHERE v.range_code = r."RangeCode"
   AND d."DistrictName" = v.district_name;

-- Bengaluru City is the Commissionerate, not a range district. Its CP holds ADGP
-- rank, per the official page.
UPDATE "District"
   SET "IsCommissionerate" = TRUE, "RangeID" = NULL, "CommandRank" = 'ADGP'
 WHERE "DistrictName" = 'Bengaluru City';

COMMIT;

-- ---------------------------------------------------------------------------
-- DEVIATION ON RECORD: Bengaluru Urban.
-- The official KSP page lists it neither among the 7 ranges nor among the 6
-- Commissionerates. It is retained here as a Central Range district under an SP,
-- per review instruction to keep it separate from the Commissionerate concept and
-- consistent with the Wikipedia range listing. It is NOT marked a
-- Commissionerate. Its 78 generated stations therefore stay with it.
--
-- VERIFY after 034 has also run:
--   SELECT r."RangeCode", count(d.*) FROM "Range" r
--     LEFT JOIN "District" d ON d."RangeID" = r."RangeID"
--    GROUP BY 1 ORDER BY 1;
--   -- expect SR 5, WR 4, ER 4, CR 7 (6 official + Bengaluru Urban), NR 5, NER 3, BR 4
--
--   SELECT "DistrictName" FROM "District"
--    WHERE "RangeID" IS NULL AND "IsCommissionerate" = FALSE;
--   -- expect zero rows
-- ---------------------------------------------------------------------------
