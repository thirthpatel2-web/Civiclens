"""Interoperability layer: a Common Data Model that heterogeneous government-system payloads
get normalized into, plus real adapter functions demonstrating the mechanism (app.interop.adapters).

This is deliberately illustrative, not a live integration: no department has given CivicLens a
data-sharing agreement or API access (see app/integrations/ for the *outbound* submission adapters,
which are real but separately gated on credentials nobody has supplied yet - app.interop is about
the opposite direction, normalizing *inbound* shapes, and ships its own realistic fixture payloads
rather than pretending to poll a live feed that does not exist).
"""
