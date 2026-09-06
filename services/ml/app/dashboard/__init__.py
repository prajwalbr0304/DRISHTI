"""Rollup-backed dashboard summary.

Serves the pure-count KPI cards from `mv_case_daily` instead of the base tables.
`/performance/overview` costs seven sequential aggregates over
CaseMaster JOIN Unit JOIN CaseStatusMaster, and with no unit/district filter each is
a full scan — survivable for ten demo seats, not for 1,046 command seats plus
~10,700 IO seats all opening a board.

The rollup is a DERIVED ARTIFACT under the case-derived-analytics policy, so this
module refuses to serve one whose attestation is not current rather than returning
figures computed under a superseded policy.
"""
