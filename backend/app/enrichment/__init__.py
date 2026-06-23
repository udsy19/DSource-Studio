"""Material-level enrichment — extract structured material attributes from a product's image +
title + description via a novelty-gated vision-LLM router (cheap Gemini for near-duplicates of
already-enriched products, Claude for novel/first-seen). Every attribute carries its own
confidence + source, and 'missing' is explicit — the NEVER-fake rule, enforced in the schema.
"""
