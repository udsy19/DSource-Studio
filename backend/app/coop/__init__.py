"""Cooperative-contract discount-band connector.

Parses public cooperative / state purchasing furniture contracts that publish pricing as
"X% off manufacturer's published list price", and extracts the real per-product-line
discount bands so the quote engine can compute net from list using contract discounts
instead of assumed ones.
"""
