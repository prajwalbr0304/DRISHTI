"""Digital-evidence platform (Phase 5).

Already-digital synthetic evidence files live in a PRIVATE Amazon S3 bucket;
only structured, MANUALLY entered metadata + provenance live in PostgreSQL.
File bytes never touch PostgreSQL and are never parsed (no OCR / transcription /
extraction / image recognition). A file upload never triggers a prediction.

Browser -> FastAPI -> PostgreSQL/S3 is the only data path: the browser gets
short-lived, exact-object pre-signed URLs the API mints; it never receives AWS
credentials.
"""
