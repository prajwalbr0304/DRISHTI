"""Financial money-trail analysis (Phase 11 / doc 04 §5-7).

The money sub-graph (FinancialAccount nodes, FinancialTransaction directed
weighted edges) analysed alongside the people graph:

  * trace      — multi-hop transaction tracing (recursive CTE + cycle guard),
                 returned as a directed weighted flow for a Sankey.
  * detection  — batch jobs that FLAG structuring / layering / circular patterns
                 onto FinancialTransaction.IsFlagged + FlagReason and surface
                 AlertHistory rows, with a ModelVersion + inference audit.
  * unified    — when a FinancialAccount has an EntityID, its node joins the same
                 canvas as its owner (people + money as one network; the tables
                 are NOT merged, the nodes are just typed by kind).

Everything is gated server-side behind the 'money_trail' permission (financial
data is sensitive) and returns provenance (record ids) on every finding.
"""
