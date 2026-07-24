"""Offline ingestion pipeline (Chain of Responsibility).

Fetch -> validate + checksum -> normalize -> load analytics -> build the semantic
layer -> embed -> version. Idempotent and versioned: re-running the same data is a
no-op. The semantic-layer *content* (descriptions, synonyms, units, few-shot SQL)
is curated in ``definitions.py`` and never derived from fetched data, so poisoned
source data cannot poison what the model is grounded on (LLM04/LLM08/ASI06).
"""
