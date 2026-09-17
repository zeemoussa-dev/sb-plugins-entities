"""The Entities registry -- `Settings/Entities.md`, the Customer/Partner
discovery store the company-review Hermes Skills read and write.

Ported from the framework's `VaultManager` Entities block with its behaviour
and on-disk format unchanged: the Skills parse this file, so a rendered file
must stay byte-for-byte what they expect.
"""
from __future__ import annotations

ENTITIES_FILE = "Settings/Entities.md"
SECTIONS = ("customer", "partner")

_KNOWN_FIELDS = {"Company Name", "Aliases", "Affiliate of", "Created", "Ignore", "Domain", "Deleted"}

_HEADER = [
    "# Entities",
    "",
    "Step 1 of the company/partner discovery sequence -- mechanical,",
    "domain-based grouping only, no LLM, no judgment about which of",
    "these are real Customers vs. Partners vs. noise.",
    "",
    "**Edit this file by hand.** `Created`/`Ignore` are Yes/No flags a",
    "later pipeline reads -- set `Ignore: Yes` instead of deleting an",
    "entry (a notification sender, a one-off vendor -- not a real",
    "business relationship); leave `Created: No` until that later,",
    "separate pipeline has actually made the hub note for it. Use",
    "`Aliases` to merge a duplicate that slipped through under a",
    "different domain (rare -- domain grouping already prevents most",
    "of this). Move real partners into `## Partners` below.",
    "",
    "## Companies",
    "",
]


class EntityNotFoundError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"No entity named {name!r}")


class DuplicateEntityError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"An entity named {name!r} already exists")


def parse_entities(content: str) -> list[dict]:
    section = None
    entries: list[dict] = []
    current: dict | None = None
    for line in content.splitlines():
        if line.startswith("## Companies"):
            section = "customer"
            continue
        if line.startswith("## Partners"):
            section = "partner"
            continue
        if line.startswith("### "):
            if current is not None:
                entries.append(current)
            current = {"section": section, "heading": line[4:].strip(), "fields": {}}
            continue
        stripped = line.strip()
        if current is not None and stripped and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            if key in _KNOWN_FIELDS:
                current["fields"][key] = value.strip()
    if current is not None:
        entries.append(current)
    return entries


def _render_entry(lines: list[str], entry: dict) -> None:
    fields = entry["fields"]
    lines.append(f"### {entry['heading']}")
    lines.append("")
    lines.append(f"\tCompany Name: {fields.get('Company Name', '')}")
    lines.append("")
    lines.append(f"\tAliases: {fields.get('Aliases', '')}")
    lines.append("")
    lines.append(f"\tAffiliate of: {fields.get('Affiliate of', '')}")
    lines.append("")
    lines.append(f"\tCreated: {fields.get('Created', 'No')}")
    lines.append("")
    lines.append(f"\tIgnore: {fields.get('Ignore', 'No')}")
    lines.append("")
    lines.append(f"\tDomain: {fields.get('Domain', '')}")
    lines.append("")
    # A hard delete would drop the row's Domain from the "already tracked" set
    # the discovery Skill checks, so a noise domain would just be rediscovered
    # on the next scan. Deleted: Yes keeps the row and its Domain instead.
    lines.append(f"\tDeleted: {fields.get('Deleted', 'No')}")
    lines.append("")
    lines.append("")


def render_entities(entries: list[dict]) -> str:
    lines = list(_HEADER)
    for entry in entries:
        if entry["section"] == "customer":
            _render_entry(lines, entry)
    lines.append("## Partners")
    lines.append("")
    for entry in entries:
        if entry["section"] == "partner":
            _render_entry(lines, entry)
    return "\n".join(lines)


def _to_public(entry: dict) -> dict:
    fields = entry["fields"]
    return {
        "name": fields.get("Company Name") or entry["heading"],
        "section": entry["section"],
        "aliases": fields.get("Aliases", ""),
        "affiliate_of": fields.get("Affiliate of", ""),
        "created": fields.get("Created", "No") == "Yes",
        "ignore": fields.get("Ignore", "No") == "Yes",
        "domain": fields.get("Domain", ""),
    }


def _find(entries: list[dict], name: str) -> dict | None:
    key = name.strip().lower()
    for entry in entries:
        if (entry["fields"].get("Company Name") or entry["heading"]).strip().lower() == key:
            return entry
    return None


class EntitiesRegistry:
    def __init__(self, api) -> None:
        self._api = api

    def _load(self) -> list[dict]:
        raw = self._api.data.read_text(ENTITIES_FILE)
        return [] if raw is None else parse_entities(raw)

    def _save(self, entries: list[dict]) -> None:
        self._api.data.write_text(ENTITIES_FILE, render_entities(entries))

    def list_entities(self) -> list[dict]:
        # Soft-deleted rows stay in the file (see delete_entity) but never surface.
        return [_to_public(entry) for entry in self._load() if entry["fields"].get("Deleted", "No") != "Yes"]

    def create_entity(self, name: str, section: str, domain: str = "", aliases: str = "", affiliate_of: str = "") -> dict:
        if section not in SECTIONS:
            raise ValueError(f"section must be 'customer' or 'partner', got {section!r}")
        entries = self._load()
        if _find(entries, name) is not None:
            raise DuplicateEntityError(name)
        entry = {
            "section": section,
            "heading": name.strip(),
            "fields": {
                "Company Name": name.strip(), "Aliases": aliases, "Affiliate of": affiliate_of,
                "Created": "No", "Ignore": "No", "Domain": domain,
            },
        }
        entries.append(entry)
        self._save(entries)
        return _to_public(entry)

    def update_entity(self, name: str, patch: dict) -> dict:
        entries = self._load()
        target = _find(entries, name)
        if target is None:
            raise EntityNotFoundError(name)
        fields = target["fields"]
        if "name" in patch:
            new_name = patch["name"].strip()
            if new_name and new_name.lower() != (fields.get("Company Name") or target["heading"]).strip().lower():
                if _find(entries, new_name) is not None:
                    raise DuplicateEntityError(new_name)
                target["heading"] = new_name
                fields["Company Name"] = new_name
        if "section" in patch and patch["section"] in SECTIONS:
            target["section"] = patch["section"]
        if "aliases" in patch:
            fields["Aliases"] = patch["aliases"]
        if "affiliate_of" in patch:
            fields["Affiliate of"] = patch["affiliate_of"]
        if "domain" in patch:
            fields["Domain"] = patch["domain"]
        if "ignore" in patch:
            fields["Ignore"] = "Yes" if patch["ignore"] else "No"
        self._save(entries)
        return _to_public(target)

    def delete_entity(self, name: str) -> None:
        """Soft delete: Deleted: Yes, plus Ignore: Yes for any discovery Skill
        not yet redeployed with the Deleted field."""
        entries = self._load()
        target = _find(entries, name)
        if target is None:
            raise EntityNotFoundError(name)
        target["fields"]["Deleted"] = "Yes"
        target["fields"]["Ignore"] = "Yes"
        self._save(entries)
