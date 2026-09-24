"""Customer resolution: the `entities.customers` service and Cockpit's
customer enricher.

A Thread or Meeting carries its customer as a `customer/<slug>` tag; the
display name comes from the Customer (or Partner) hub note's own `name`,
never from reversing the slug, which gets names like "Al Ain" wrong.
"""
from __future__ import annotations


class Customers:
    def __init__(self, api) -> None:
        self._api = api

    def name_by_tag(self) -> dict[str, str]:
        """Every hub tag (`customer/<slug>`, `partner/<slug>`) -> the hub note's `name`.
        Build it once and pass it to `customer_from_tags` when resolving many notes."""
        mapping: dict[str, str] = {}
        # Every note, not the by-name map: a hub sharing its name with another note
        # is missing from that map, and its whole Customer then resolves to nothing
        # (framework BUG-076, Plugin API v5).
        for entry in self._api.vault.entries():
            if entry["frontmatter"].get("type") not in ("Customer", "Partner"):
                continue
            name = entry["frontmatter"].get("name")
            if not name:
                continue
            for tag in entry["tags"]:
                mapping.setdefault(tag, name)
        return mapping

    def customer_from_tags(self, tags: list[str], lookup: dict[str, str] | None = None) -> str | None:
        """THE Customer for a note, never a Partner: the lookup holds both hub
        kinds, so without the `customer/` filter a Thread tagged
        `["partner/g42", "customer/mubadala"]` returned "G42"."""
        names = self.name_by_tag() if lookup is None else lookup
        for tag in tags:
            if tag.startswith("customer/") and tag in names:
                return names[tag]
        return None

    def subject_enricher(self, subject_kind: str, frontmatter: dict, tags: list[str]) -> dict:
        customer = self.customer_from_tags(tags)
        return {"customer": customer} if customer else {}
