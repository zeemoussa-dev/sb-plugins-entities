"""Customer resolution: the `entities.customers` service and Cockpit's
customer enricher.

A Thread or Meeting carries its customer as a `customer/<slug>` tag; the
display name comes from the Customer (or Partner) hub note's own `name`,
never from reversing the slug, which gets names like "Al Ain" wrong.
"""
from __future__ import annotations

from . import commitment, insight
from .opportunities import Opportunities


class Customers:
    # The commitment fields `set_commitment` accepts, so a caller can leave out one
    # an older Entities does not know rather than have the whole write refused.
    COMMITMENT_FIELDS = tuple(commitment.KEYS)

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

    def commitment(self, customer_stem: str) -> dict | None:
        """The signed Azure commitment on a Customer's (or an affiliate's) hub
        note, or None when it holds none."""
        service = Opportunities(self._api)
        return commitment.from_frontmatter(service._frontmatter_of(service.hub_path(customer_stem)))

    def set_commitment(self, customer_stem: str, value: dict | None) -> dict | None:
        """Writes the commitment's `macc_*` keys on the hub note, or removes them
        all for None; nothing else in the note changes. Returns it as now read."""
        path = Opportunities(self._api).hub_path(customer_stem)
        commitment.write(path, value)
        return self.commitment(customer_stem)

    def _hub_paths(self, stems: list[str] | None) -> dict[str, "Path"]:
        """stem -> hub note for these stems (every hub when None), from one walk.
        A stem that is no hub, or names more than one, is left out."""
        found: dict[str, list] = {}
        for hub in Opportunities(self._api)._hubs():
            found.setdefault(hub["stem"], []).append(hub["path"])
        wanted = found if stems is None else {stem: found.get(stem, []) for stem in stems}
        return {stem: paths[0] for stem, paths in wanted.items() if len(paths) == 1}

    def commitments(self, stems: list[str] | None = None) -> dict[str, dict | None]:
        """`commitment` for many hubs at once -- stem -> commitment or None -- for
        a page that shows every customer. Unknown or ambiguous stems are left out."""
        service = Opportunities(self._api)
        return {stem: commitment.from_frontmatter(service._frontmatter_of(path))
                for stem, path in self._hub_paths(stems).items()}

    def insights(self, stems: list[str] | None = None) -> dict[str, dict | None]:
        """`insight` for many hubs at once -- stem -> insight or None. Unknown or
        ambiguous stems are left out; a note whose json does not parse raises, as
        `insight` does."""
        return {stem: insight.read(path) for stem, path in self._hub_paths(stems).items()}

    def insight(self, customer_stem: str) -> dict | None:
        """The Core42 Insight terms for a hub -- `{terms, note}` -- kept in
        its own `<stem> - Insight.md` note beside the hub, or None when it has none."""
        return insight.read(Opportunities(self._api).hub_path(customer_stem))

    def set_insight(self, customer_stem: str, value: dict | None) -> dict | None:
        """Writes the Insight note (None deletes it); the hub itself never changes.
        Returns what `insight` now reads."""
        hub = Opportunities(self._api)._hub(customer_stem)
        insight.write(hub["path"], hub["name"], value)
        return self.insight(customer_stem)

    def subject_enricher(self, subject_kind: str, frontmatter: dict, tags: list[str]) -> dict:
        customer = self.customer_from_tags(tags)
        return {"customer": customer} if customer else {}
