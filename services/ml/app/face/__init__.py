"""Face recognition: 1:N search of a probe photo against the canonical person
gallery (PersonFaceEmbedding, pgvector HNSW cosine).

A match is a LEAD for human review, never an identity assertion — confirming one
raises an EntityResolutionCandidate (Method='face') exactly like every other
matching signal in this system. Nothing auto-merges.
"""
