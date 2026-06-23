"""WELL-Ranked Catalog layer — Dsource Studio pillar.

"Intelligent Catalogue Matching + Sustainability & WELL Scoring": ranks catalog
products by a composite of WELL compliance, lead time, and cost so the studio can
surface the most healthy/sustainable + commercially sensible option per category.

This is an additive layer over the read-only Product spine (app/models.py): a new
ProductCert table is joined to Product on `sku`. US / USD throughout.
"""
