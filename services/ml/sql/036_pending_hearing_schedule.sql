-- DRISHTI migration 036: give cases awaiting trial an adjourned-to hearing date.
--
-- WHY
-- CourtEvent.ScheduledAt was NULL on all 64,391 rows and every row carried an
-- OccurredAt, so nothing in the corpus was scheduled-but-not-yet-heard. The 10,322
-- cases at "Pending Trial" each had hearing HISTORY and no next date. That made the
-- "Next court date" KPI impossible to compute rather than merely unaggregated: an
-- aggregate over it would return an empty answer dressed as a measurement, so the
-- card shipped in an honest `pending` state.
--
-- A case the court holds and has not judged has, in reality, been adjourned TO a
-- date. This writes that date. It is a gap in the generator, not an invention:
-- datagen/court_outcomes.py now emits the same row for newly generated corpora
-- (build_case_court_outcomes, the `else` branch beside the judgment event), so a
-- rebuild produces this without the backfill.
--
-- SHAPE
-- ScheduledAt set + OccurredAt NULL is what marks a hearing as still to come, and
-- is what the /casework/hearings/next aggregate selects on. Every other row in the
-- table has the opposite pair, so the two populations cannot be confused.
--
-- ANCHORED TO THE DATA, NOT TO wall-clock now()
-- The corpus is synthetic 2021-2026. Scheduling relative to now() would place court
-- dates years after the case history and make the interval meaningless; it would
-- also drift every day the demo is not rebuilt. Each date is derived from THAT
-- CASE's own last court event, so the adjournment interval is realistic and the
-- data is stable. The endpoint therefore reports "days until" relative to the
-- corpus as-of date and states that as_of, exactly as /performance and /outcomes do.
--
-- PURELY ADDITIVE + PRECISELY REVERSIBLE
-- No pre-existing row is read for update or deleted. Every inserted row is stamped
-- Detail->>'migration' = '036', so the rollback deletes exactly this set.

BEGIN;

-- Idempotent: re-running must not give a case two next hearings.
DELETE FROM "CourtEvent" WHERE "Detail" ->> 'migration' = '036';

INSERT INTO "CourtEvent" ("CaseMasterID", "CourtID", "EventType", "ScheduledAt",
                          "OccurredAt", "Outcome", "Detail")
SELECT p."CaseMasterID",
       p."CourtID",
       'hearing',
       -- Anchored on the LATER of this case's last activity and the corpus end,
       -- plus a 21-75 day adjournment interval.
       --
       -- Anchoring on the case's own last event alone was wrong and the data said
       -- so: it produced next hearings from 2021 onward, because a case pending
       -- since 2021 has no court activity after 2021 and the corpus never models
       -- the intervening chain of adjournments. That put most "next" hearings in
       -- the past and reproduced the very gap this migration exists to close.
       --
       -- Clamping to the corpus end states the honest thing instead: as at the end
       -- of the record, here is when each pending case next sits. A long-pending
       -- case getting a date shortly after the corpus end is exactly what a real
       -- adjournment chain would leave behind.
       --
       -- The interval is derived from the case id rather than random() so
       -- re-running on the same corpus yields the same calendar, which keeps
       -- fixtures and screenshots stable.
       GREATEST(p."last_at", (SELECT max("OccurredAt") FROM "CourtEvent"))
           + make_interval(days => 21 + (p."CaseMasterID" % 55)),
       NULL,                       -- not yet heard: this is the whole point
       'scheduled',
       jsonb_build_object('synthetic', TRUE, 'adjourned_to', TRUE,
                          'migration', '036')
  FROM (
        SELECT cm."CaseMasterID",
               -- The court that last handled it. A pending case can have events
               -- across more than one court row; the most recent one is the court
               -- that will next sit.
               (SELECT ce2."CourtID"
                  FROM "CourtEvent" ce2
                 WHERE ce2."CaseMasterID" = cm."CaseMasterID"
                   AND ce2."CourtID" IS NOT NULL
                 ORDER BY ce2."OccurredAt" DESC NULLS LAST
                 LIMIT 1) AS "CourtID",
               max(ce."OccurredAt") AS "last_at"
          FROM "CaseMaster" cm
          JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID"
          JOIN "CourtEvent" ce ON ce."CaseMasterID" = cm."CaseMasterID"
         WHERE st."CaseStatusName" = 'Pending Trial'
           AND ce."OccurredAt" IS NOT NULL
         GROUP BY cm."CaseMasterID"
       ) p
 WHERE p."last_at" IS NOT NULL;

-- Partial index on exactly the population the aggregate scans. Without it, "next
-- scheduled hearing for these districts" seq-scans all 74k CourtEvent rows to find
-- the ~10k that are pending.
CREATE INDEX IF NOT EXISTS "idx_courtevent_pending_hearing"
    ON "CourtEvent" ("ScheduledAt", "CaseMasterID")
 WHERE "OccurredAt" IS NULL AND "ScheduledAt" IS NOT NULL;

COMMENT ON COLUMN "CourtEvent"."ScheduledAt" IS
    'When the event is scheduled to happen. Set with OccurredAt NULL for a hearing that has been adjourned to a date but not yet heard; that pair is what /casework/hearings/next selects on. Historical rows carry OccurredAt with ScheduledAt NULL.';

COMMIT;

-- ---------------------------------------------------------------------------
-- Verification (expect: pending > 0, orphans = 0, one per case)
--   SELECT count(*) FROM "CourtEvent"
--    WHERE "OccurredAt" IS NULL AND "ScheduledAt" IS NOT NULL;
--
--   -- every pending hearing must belong to a Pending Trial case
--   SELECT count(*) FROM "CourtEvent" ce
--     JOIN "CaseMaster" cm ON cm."CaseMasterID"=ce."CaseMasterID"
--     JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID"
--    WHERE ce."Detail"->>'migration'='036' AND st."CaseStatusName" <> 'Pending Trial';
--
--   -- exactly one next hearing per case
--   SELECT count(*) FROM (
--     SELECT "CaseMasterID" FROM "CourtEvent" WHERE "Detail"->>'migration'='036'
--      GROUP BY 1 HAVING count(*) > 1) q;
--
--   -- every scheduled date must be AFTER the corpus end, or it is not "next"
--   SELECT count(*) FROM "CourtEvent"
--    WHERE "Detail"->>'migration'='036'
--      AND "ScheduledAt" <= (SELECT max("OccurredAt") FROM "CourtEvent"
--                             WHERE "OccurredAt" IS NOT NULL);
-- ---------------------------------------------------------------------------
