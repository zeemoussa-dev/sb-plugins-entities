"""Entities -- a Second Brain plugin (`ADR-022`, Entities plan Phase 3).

Customers, Partners, Affiliates and Opportunities, taken out of the framework
so a second brain that has no such concept (a CFO's, say) carries none of it.

Everything this plugin needs from the framework arrives through the Plugin API
handed to `register`; it imports nothing from the framework itself.
"""
from __future__ import annotations

from .customers import Customers
from .matching import CockpitAgentMatcher
from .registry import ENTITIES_FILE, EntitiesRegistry
from .routes import build_router

# Where the People pipeline files a Person: under their company's hub folder.
COMPANY_FOLDERS = ["Work/Customers", "Work/Partners"]


def register(api) -> None:
    api.register_seed_data_file(ENTITIES_FILE)
    api.register_people_folders(COMPANY_FOLDERS)

    customers = Customers(api)
    api.provide_service("entities.customers", customers)
    api.register_subject_enricher(customers.subject_enricher)
    api.register_agent_matcher(CockpitAgentMatcher(api).match)

    api.register_router(build_router(EntitiesRegistry(api)))
