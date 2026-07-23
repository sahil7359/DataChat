"""Ports — the interfaces the domain defines and infrastructure implements.

Each port is small and role-specific (Interface Segregation): the executor knows
nothing about validation, the catalog knows nothing about LLMs.
"""
