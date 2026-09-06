-- Rollback for DRISHTI migration 033 (Wing and Range roster seed).
--
-- Clears range membership and Commissionerate marking, then removes the roster
-- rows. Run AFTER 034's rollback: 034 creates District rows that reference these
-- Range rows, and seats anchored to a wing or range must be gone first.
--
-- Refuses to delete a Range or Wing that any users row still anchors to, so a
-- partial rollback cannot orphan a provisioned seat.

BEGIN;

UPDATE "District"
   SET "RangeID" = NULL, "IsCommissionerate" = FALSE, "CommandRank" = NULL;

UPDATE "Range" SET "HQDistrictID" = NULL;

DELETE FROM "WingCrimeHead"
 WHERE "WingID" IN (SELECT "WingID" FROM "Wing"
                     WHERE "WingCode" IN ('LO','CTS','INT','ISC','TRF','CID'));

DELETE FROM "Wing"
 WHERE "WingCode" IN ('LO','CTS','INT','ISC','TRF','CID')
   AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."wing_id" = "Wing"."WingID");

DELETE FROM "Range"
 WHERE "RangeCode" IN ('SR','WR','ER','CR','NR','NER','BR')
   AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."range_id" = "Range"."RangeID");

COMMIT;

-- Verification: anything left is still referenced by a seat.
-- SELECT 'wing' AS kind, "WingCode" AS code FROM "Wing"
--  UNION ALL SELECT 'range', "RangeCode" FROM "Range";
