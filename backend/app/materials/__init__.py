"""Material → maintenance/durability derivation — Phase 2 computed attribute layer.

Maps a material family (+ optional finish, + optional per-SKU measured overrides) to six
durability/maintenance axes, each grounded in a real industry standard (Martindale/Wyzenbeek,
PEI, AC rating, Janka, ACT cleaning codes, GREENGUARD). This is COMPUTED — not scraped, not an
LLM call. Honest-data rule: where we have no per-SKU lab measurement the basis is reported as
`derived_proxy` (from material class) or `estimated`, never dressed up as `measured_standard`.
"""
