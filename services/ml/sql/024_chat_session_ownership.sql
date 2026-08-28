-- DRISHTI migration 024: bind Ask DRISHTI threads to an authenticated subject.
--
-- Catalyst user ids are opaque strings, while ChatSession.UserID is an integer
-- foreign key into the synthetic/local users table.  OwnerSubject therefore
-- stores a namespaced, stable external subject (for example catalyst:<id> or a
-- hashed local-demo actor) without weakening either identity model.
--
-- Existing rows remain NULL deliberately: they predate authenticated ownership
-- and must not become visible to every user.  New application writes always set
-- OwnerSubject and all history/continuation reads filter by it.

ALTER TABLE "ChatSession"
    ADD COLUMN IF NOT EXISTS "OwnerSubject" VARCHAR(160);

CREATE INDEX IF NOT EXISTS "idx_chatsession_owner_subject"
    ON "ChatSession" ("OwnerSubject", "CreatedAt" DESC);

COMMENT ON COLUMN "ChatSession"."OwnerSubject" IS
    'Namespaced authenticated owner subject. NULL denotes a legacy unowned row and is never returned by private chat-history APIs.';
