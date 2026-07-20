"""Organizational hierarchy, rank-to-role-scope mapping and server-side scope
derivation (Prompt 20 Part B).

This package composes the existing functional roles (admin/permissions.py) with
a documented, SYNTHETIC police rank -> functional role + organizational scope
mapping, and derives the caller's state/range/district/subdivision/station/
assigned-case scope SERVER-SIDE from the trusted Catalyst identity + assignment
records — never from a browser-supplied district header.

Real directory/SSO/rank synchronisation with the Karnataka Police establishment
is explicitly post-hackathon; this is a synthetic demo mapping.
"""
