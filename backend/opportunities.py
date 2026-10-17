"""The `entities.opportunities` service: a Customer's sales pipeline, which is
its Opportunity notes in the vault -- its own and its affiliates'.

This plugin owns the `opportunity` Template, so it is the one that writes those
notes; another plugin (the Azure Cost Manager first) asks for this service and
never writes them itself. The Plugin API reads notes but has no vault write, so
the writes are this module's own few lines in the same plain format the vault
engine writes: quoted frontmatter values, flow lists, `## ` sections.

Nothing a caller passes is joined into a path. Hubs and opportunities are looked
up among notes that exist, and a new note's title must already be a valid file
name, because the Template says the file name equals the title.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import date
from pathlib import Path

from .registry import EntitiesRegistry

# The Template's content, kept here because an installed plugin carries its
# backend but not its `templates/` folder; a test pins these to
# `templates/opportunity/Template.json` so the two cannot drift.
TEMPLATE_VERSION = 3
KEY_ORDER = [
    "type", "id", "title", "customer", "status", "stage", "product", "route", "draws_against",
    "partner", "technologies", "billing_profile", "consumption_start", "expected_consumption",
    "expected_monthly_usd", "created", "updated", "tags",
]
DEFAULTS = {
    "type": "Opportunity", "status": "Open", "stage": "Identified", "product": [], "route": "unknown",
    "draws_against": "", "partner": [], "technologies": [], "billing_profile": "", "consumption_start": "",
    "expected_consumption": "", "expected_monthly_usd": "", "updated": "{today}", "tags": ["kind/opportunity"],
}
ENUMS = {
    "status": ["Open", "Won", "Lost", "On Hold", "Disengaged"],
    "stage": ["Identified", "Qualified", "Proposed", "Committed", "Closed"],
    "product": ["azure", "private-cloud", "gpuaas", "compass", "m365", "services", "marketplace-isv", "other"],
    "route": ["direct-ea-mca", "csp", "marketplace-private-offer", "marketplace-mpo", "unknown"],
}
SECTIONS = ["Summary", "Consumption Plan", "Actions", "Related", "History & Captures"]
CHILDREN = [
    {"suffix": "history", "type": "History", "tag": "kind/history", "label": "History"},
    {"suffix": "captures", "type": "Captures", "tag": "kind/captures", "label": "Captures"},
]
# The `customer` Template, pinned the same way, for `create_affiliate`.
CUSTOMER_DEFAULTS = {"type": "Customer", "affiliate_of": "", "tags": ["kind/customer"]}
CUSTOMER_SECTIONS = ["Summary", "Personal Notes", "Actions", "Related", "Affiliates", "History & Captures"]
AFFILIATES_SECTION = "Affiliates"
PLAN_SECTION = "Consumption Plan"
LINK_BACK_SECTION = "Opportunities"
HISTORY_SECTION = "Log"

# What `create` and `update` may set. `type`, `id`, `title`, `customer`, the
# dates and the tags are the Template's to set, never a caller's.
EDITABLE = [
    "status", "stage", "product", "route", "draws_against", "partner", "technologies",
    "billing_profile", "consumption_start", "expected_consumption", "expected_monthly_usd",
]
_LIST_FIELDS = ("product", "partner", "technologies")
_CLOSED_STATUSES = ("Won", "Lost")
_DRAWING_ROUTES = ("direct-ea-mca", "marketplace-private-offer", "marketplace-mpo")

_FILENAME_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PLAN_ROW = re.compile(r"^\|\s*(\d{4}-\d{2})\s*\|\s*\$?\s*([\d,]+)\s*\|\s*$")
_FRONTMATTER_KEY = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):")
_EXTENDED_PREFIX = "\\\\?\\"


class OpportunityError(ValueError):
    """What was asked breaks one of the Template's rules; the message says which."""


class OpportunityNotFound(OpportunityError):
    pass


def _long(path) -> str:
    """`path` in a form Windows opens past its 260-character limit. An
    Opportunity's title appears twice in its path (its folder and its file), and
    an affiliate's sits three folders deeper than a Customer's, so real notes
    cross that limit; a plain open() then fails on a file that exists."""
    absolute = os.path.abspath(str(path))
    if os.name == "nt" and not absolute.startswith(_EXTENDED_PREFIX):
        return _EXTENDED_PREFIX + absolute
    return absolute


def _exists(path: Path) -> bool:
    return os.path.exists(_long(path))


def _read_text(path: Path) -> str:
    with open(_long(path), encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: Path, text: str) -> None:
    os.makedirs(_long(path.parent), exist_ok=True)
    with open(_long(path), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _today() -> str:
    return date.today().isoformat()


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _format_value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(value)


def _frontmatter_text(frontmatter: dict) -> str:
    lines = ["---"] + [f"{key}: {_format_value(value)}" for key, value in frontmatter.items()]
    return "\n".join(lines + ["---"]) + "\n"


def _tag_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9/]+", "-", text.lower()).strip("-") or "untitled"


def _section_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    """(heading line, end) of `## <name>`, end being the next `## ` heading."""
    heading = f"## {name}"
    start = next((i for i, line in enumerate(lines) if line.rstrip() == heading), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def _section_lines(text: str, name: str) -> list[str]:
    lines = text.split("\n")
    bounds = _section_bounds(lines, name)
    if bounds is None:
        return []
    return [line for line in lines[bounds[0] + 1:bounds[1]] if line.strip()]


def _with_section(text: str, name: str, content: str, *, after: str | None = None) -> str:
    """`text` with `## <name>` holding exactly `content`. A missing section is
    added after the `after` section when there is one, else at the end."""
    lines = text.split("\n")
    block = [f"## {name}", "", *content.strip("\n").split("\n"), ""] if content.strip() else [f"## {name}", ""]
    bounds = _section_bounds(lines, name)
    if bounds is not None:
        start, end = bounds
        lines[start:end] = block
        return "\n".join(lines)
    anchor = _section_bounds(lines, after) if after else None
    if anchor is not None:
        lines[anchor[1]:anchor[1]] = block
        return "\n".join(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines + [""] + block)


def _with_line_appended(text: str, name: str, line: str) -> str:
    """`line` added at the end of `## <name>`, a blank line from the one before,
    the way a History log is kept. Adds the section when the note lacks it."""
    lines = text.split("\n")
    bounds = _section_bounds(lines, name)
    if bounds is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines + ["", f"## {name}", "", line, ""])
    start, end = bounds
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = ["", line]
    return "\n".join(lines).rstrip("\n") + "\n"


def with_frontmatter(text: str, values: dict, key_order: list[str] = (), remove: tuple[str, ...] = ()) -> str:
    """`text` with these frontmatter keys set and the `remove` keys gone, every
    other line left exactly as it was. A key the note lacks goes before the
    next key `key_order` puts after it, else at the end of the frontmatter."""
    if not text.startswith("---\n"):
        raise OpportunityError("this note has no frontmatter to update")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise OpportunityError("this note's frontmatter is not closed")
    lines = text[4:end].split("\n")
    keys = [(_FRONTMATTER_KEY.match(line) or [None, None])[1] for line in lines]
    kept = [(key, line) for key, line in zip(keys, lines) if key is None or key not in remove]
    keys, lines = [key for key, _ in kept], [line for _, line in kept]
    for key, value in values.items():
        line = f"{key}: {_format_value(value)}"
        if key in keys:
            lines[keys.index(key)] = line
            continue
        position = len(lines)
        for later in key_order[key_order.index(key) + 1:] if key in key_order else []:
            if later in keys:
                position = keys.index(later)
                break
        lines.insert(position, line)
        keys.insert(position, key)
    return "---\n" + "\n".join(lines) + text[end:]


def _notes_in_own_folders(folder: Path) -> list[Path]:
    """`<folder>/<X>/<X>.md` for every subfolder that holds its own note. A
    `_`-prefixed folder is the vault's archive convention and is skipped."""
    if not os.path.isdir(_long(folder)):
        return []
    paths = []
    with os.scandir(_long(folder)) as children:
        for child in children:
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            note = folder / child.name / f"{child.name}.md"
            if _exists(note):
                paths.append(note)
    return sorted(paths, key=lambda p: p.stem.lower())


def _link_into_section(hub_path: Path, section: str, wikilink: str) -> None:
    """`- <wikilink>` added to a hub's section once, as the engine's link-back does."""
    text = _read_text(hub_path)
    existing = _section_lines(text, section)
    if any(wikilink in line for line in existing):
        return
    _write_text(hub_path, _with_section(text, section, "\n".join([*existing, f"- {wikilink}"])))


def _hub_record(path: Path, frontmatter: dict, tags: list, owner_of: str | None) -> dict:
    tag = next((t for t in tags if str(t).startswith("customer/")), None)
    return {
        "name": _text(frontmatter.get("name")) or path.stem,
        "stem": path.stem,
        "tag": tag or f"customer/{_tag_slug(path.stem)}",
        "path": path,
        "customer_stem": owner_of,
        "aliases": [_text(a) for a in frontmatter.get("aliases") or [] if _text(a)]
        if isinstance(frontmatter.get("aliases"), list) else [],
    }


# -- the Consumption Plan -------------------------------------------------------


def plan_table(plan: list[dict]) -> str:
    rows = [f"| {row['month']} | {row['usd']} |" for row in plan]
    return "\n".join(["| Month | USD |", "|---|---|", *rows])


def parse_plan(section: str | None) -> list[dict]:
    plan = []
    for line in str(section or "").splitlines():
        match = _PLAN_ROW.match(line.strip())
        if match and _MONTH.match(match.group(1)):
            plan.append({"month": match.group(1), "usd": int(match.group(2).replace(",", ""))})
    return sorted(plan, key=lambda row: row["month"])


def _usd(value, what: str) -> int:
    if isinstance(value, bool):
        raise OpportunityError(f"{what} must be a whole number of USD")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*", value):
        value = int(value)
    if not isinstance(value, int) or value < 0:
        raise OpportunityError(f"{what} must be a whole, non-negative number of USD, not {value!r}")
    return value


def validated_plan(plan) -> list[dict]:
    if not isinstance(plan, list):
        raise OpportunityError("plan must be a list of {month, usd}")
    rows, seen = [], set()
    for row in plan:
        if not isinstance(row, dict):
            raise OpportunityError("each plan row is {month, usd}")
        month = _text(row.get("month"))
        if not _MONTH.match(month):
            raise OpportunityError(f"plan month must be YYYY-MM, not {row.get('month')!r}")
        if month in seen:
            raise OpportunityError(f"plan has {month} twice")
        seen.add(month)
        rows.append({"month": month, "usd": _usd(row.get("usd"), f"plan USD for {month}")})
    return sorted(rows, key=lambda r: r["month"])


# -- the service ------------------------------------------------------------------


class Opportunities:
    def __init__(self, api) -> None:
        self._api = api

    # -- hubs -----------------------------------------------------------------

    def _hubs(self) -> list[dict]:
        """Every Customer hub, a top-level one at `Work/Customers/<C>/<C>.md` and
        an affiliate at `Work/Customers/<C>/Affiliates/<A>/<A>.md`. Found by where
        the note sits, the layout the Template's `parent` describes."""
        hubs = []
        for entry in self._api.vault.entries():
            if entry["frontmatter"].get("type") != "Customer":
                continue
            path = Path(entry["path"])
            parts = path.parts
            if path.parent.name != entry["stem"] or len(parts) < 4:
                continue
            if parts[-3] == "Customers" and parts[-4] == "Work":
                owner_of = None
            elif len(parts) >= 6 and parts[-3] == "Affiliates" and parts[-5] == "Customers" and parts[-6] == "Work":
                owner_of = parts[-4]
            else:
                continue
            hubs.append(_hub_record(path, entry["frontmatter"], entry["tags"], owner_of))
        # An affiliate created a moment ago is not in the index until its next
        # rebuild; it must list at once, as a new opportunity does.
        indexed = {hub["path"] for hub in hubs}
        for top in [hub for hub in hubs if hub["customer_stem"] is None]:
            for path in _notes_in_own_folders(top["path"].parent / "Affiliates"):
                if path in indexed:
                    continue
                frontmatter, _ = self._api.vault.read_note(path)
                if _text(frontmatter.get("type")) == "Customer":
                    tags = frontmatter.get("tags") if isinstance(frontmatter.get("tags"), list) else []
                    hubs.append(_hub_record(path, frontmatter, tags, top["stem"]))
        return hubs

    def _hub(self, stem: str, hubs: list[dict] | None = None) -> dict:
        wanted = _text(stem)
        found = [hub for hub in (hubs if hubs is not None else self._hubs()) if hub["stem"] == wanted]
        if not found:
            raise OpportunityNotFound(f"no Customer or affiliate hub named {stem!r}")
        if len(found) > 1:
            raise OpportunityError(f"more than one hub is named {stem!r}")
        return found[0]

    def hub_path(self, stem: str) -> Path:
        """Where a Customer's or an affiliate's hub note is, found among the hubs
        that exist -- never built from the stem."""
        return self._hub(stem)["path"]

    @staticmethod
    def _customer_of(hub: dict, hubs: list[dict]) -> dict | None:
        """The top-level Customer a hub belongs to: itself, or the hub of the
        folder an affiliate sits in -- None when that folder has no hub note."""
        if hub["customer_stem"] is None:
            return hub
        return next((h for h in hubs if h["customer_stem"] is None and h["stem"] == hub["customer_stem"]), None)

    def customers(self) -> list[dict]:
        hubs = self._hubs()
        result = []
        for top in sorted((h for h in hubs if h["customer_stem"] is None), key=lambda h: h["name"].lower()):
            affiliates = sorted((h for h in hubs if h["customer_stem"] == top["stem"]),
                                key=lambda h: h["name"].lower())
            result.append({
                "name": top["name"], "stem": top["stem"], "tag": top["tag"],
                "affiliates": [{"name": a["name"], "stem": a["stem"], "tag": a["tag"]} for a in affiliates],
            })
        return result

    def create_affiliate(self, customer_stem: str, name: str, aliases: list[str] | None = None) -> dict:
        """A new affiliate under a top-level Customer, made the way the company
        Skill makes one: the engine's `create()` from the `customer` Template,
        then the hub's own `customer/<slug>` tag on it and its two children
        (that Skill's backfill; the Template has no tag for "your own name"),
        the link in the parent's `## Affiliates`, and the registry row marked
        Created so discovery does not make it again."""
        hubs = self._hubs()
        parent = self._hub(customer_stem, hubs)
        if parent["customer_stem"] is not None:
            raise OpportunityError(f"{parent['name']} is itself an affiliate; affiliates sit under a top-level Customer")
        name = _text(name)
        if not name or name != str(name).strip():
            raise OpportunityError("name is required, on one line")
        stem = _FILENAME_INVALID.sub("-", name)[:120].strip(" .")
        if not stem or stem in (".", ".."):
            raise OpportunityError(f"{name!r} cannot be a file name")
        wanted_aliases = list(dict.fromkeys(_text(a) for a in (aliases or []) if _text(a)))

        taken = {stem.lower(), name.lower(), *(a.lower() for a in wanted_aliases)}
        for hub in hubs:
            if taken & {hub["stem"].lower(), hub["name"].lower(), *(a.lower() for a in hub["aliases"])}:
                raise OpportunityError(f"{name!r} is already the Customer or affiliate {hub['name']!r}")
        for entry in self._api.vault.entries():
            if entry["frontmatter"].get("type") == "Partner" and \
                    taken & {entry["stem"].lower(), _text(entry["frontmatter"].get("name")).lower()}:
                raise OpportunityError(f"{name!r} is already the Partner {entry['stem']!r}")
        registry = EntitiesRegistry(self._api)
        row = registry.find_entity(name)
        if row is not None and row["deleted"]:
            raise OpportunityError(f"{name!r} was deleted from the Entities registry; set its Deleted: No "
                                   "in Settings/Entities.md first")
        if row is not None and row["section"] != "customer":
            raise OpportunityError(f"{name!r} is registered as a {row['section']}")
        folder = parent["path"].parent / "Affiliates" / stem
        if _exists(folder):
            raise OpportunityError(f"{parent['name']} already has an affiliate folder named {stem!r}")

        # A company discovery already registered keeps its domain and aliases.
        domain = row["domain"] if row else ""
        registered_aliases = [a.strip() for a in (row["aliases"] if row else "").split(",") if a.strip()]
        all_aliases = list(dict.fromkeys([*registered_aliases, *wanted_aliases]))
        tag = f"customer/{_tag_slug(stem)}"
        frontmatter = {"type": CUSTOMER_DEFAULTS["type"], "affiliate_of": parent["stem"], "name": name}
        if domain:
            frontmatter["domain"] = domain
        if all_aliases:
            frontmatter["aliases"] = all_aliases
        frontmatter.update({"id": str(uuid.uuid4()), "title": name, "created": _today(),
                            "tags": list(dict.fromkeys([*CUSTOMER_DEFAULTS["tags"], tag]))})

        contents = {"History & Captures": "\n".join(f"- [[{stem}-{c['suffix']}|{c['label']}]]" for c in CHILDREN)}
        body = "\n" + "\n".join(f"## {section}\n\n{contents.get(section, '')}\n" for section in CUSTOMER_SECTIONS)
        _write_text(folder / f"{stem}.md", _frontmatter_text(frontmatter) + body)
        for child in CHILDREN:
            child_frontmatter = {"type": child["type"], "name": f"{name} {child['label']}",
                                 "parent": f"[[{stem}]]", "tags": [child["tag"], tag]}
            _write_text(folder / f"{stem}-{child['suffix']}.md",
                        _frontmatter_text(child_frontmatter) + f"\n# {name}\n\n")
        _link_into_section(parent["path"], AFFILIATES_SECTION, f"[[{stem}]]")

        if row is None:
            registry.create_entity(name, "customer", aliases=", ".join(all_aliases),
                                   affiliate_of=parent["name"], created=True)
        else:
            registry.update_entity(row["name"], {"affiliate_of": parent["name"], "created": True,
                                                 "aliases": ", ".join(all_aliases)})
        return {"name": name, "stem": stem, "tag": tag}

    # -- reading --------------------------------------------------------------

    @staticmethod
    def _opportunity_paths(hub: dict) -> list[Path]:
        """The notes at `<hub folder>/Opportunities/<T>/<T>.md`, read off the
        disk rather than the vault index: the index is rebuilt on its own
        schedule, and an opportunity created a moment ago must already list."""
        return _notes_in_own_folders(hub["path"].parent / "Opportunities")

    def _describe(self, path: Path, frontmatter: dict, customer: dict, affiliate: dict | None) -> dict:
        def listed(key):
            value = frontmatter.get(key)
            return [str(v) for v in value] if isinstance(value, list) else ([str(value)] if _text(value) else [])

        expected = _text(frontmatter.get("expected_monthly_usd"))
        return {
            "id": _text(frontmatter.get("id")),
            "title": _text(frontmatter.get("title")) or path.stem,
            "stem": path.stem,
            "customer": customer["name"],
            "affiliate": affiliate["name"] if affiliate else None,
            "status": _text(frontmatter.get("status")),
            "stage": _text(frontmatter.get("stage")),
            "product": listed("product"),
            "route": _text(frontmatter.get("route")),
            "partner": listed("partner"),
            "billing_profile": _text(frontmatter.get("billing_profile")),
            "consumption_start": _text(frontmatter.get("consumption_start")),
            "expected_monthly_usd": int(expected) if expected.isdigit() else None,
            "plan": parse_plan(self._api.vault.read_section(path, PLAN_SECTION)),
            "updated": _text(frontmatter.get("updated")),
        }

    def _owners_of(self, customer: dict, hubs: list[dict], include_affiliates: bool) -> list[tuple[dict, dict | None]]:
        owners = [(customer, None)]
        if include_affiliates:
            for hub in sorted((h for h in hubs if h["customer_stem"] == customer["stem"]),
                              key=lambda h: h["name"].lower()):
                owners.append((customer, hub))
        return owners

    def list_for_customer(self, customer_stem: str, include_affiliates: bool = True) -> list[dict]:
        hubs = self._hubs()
        hub = self._hub(customer_stem, hubs)
        if hub["customer_stem"] is not None:
            customer = self._customer_of(hub, hubs)
            if customer is None:
                raise OpportunityNotFound(f"{customer_stem!r} sits in a Customer folder with no hub note")
            owners = [(customer, hub)]
        else:
            owners = self._owners_of(hub, hubs, include_affiliates)
        result = []
        for customer, affiliate in owners:
            for path in self._opportunity_paths(affiliate or customer):
                frontmatter, _ = self._api.vault.read_note(path)
                if _text(frontmatter.get("type")) == "Opportunity":
                    result.append(self._describe(path, frontmatter, customer, affiliate))
        return result

    def _find(self, opportunity_id: str) -> tuple[Path, dict, dict, dict | None]:
        wanted = _text(opportunity_id)
        if not wanted:
            raise OpportunityNotFound("no opportunity id given")
        hubs = self._hubs()
        for hub in hubs:
            customer = self._customer_of(hub, hubs)
            if customer is None:
                continue
            affiliate = None if hub is customer else hub
            for path in self._opportunity_paths(hub):
                frontmatter, _ = self._api.vault.read_note(path)
                if _text(frontmatter.get("id")) == wanted and _text(frontmatter.get("type")) == "Opportunity":
                    return path, frontmatter, customer, affiliate
        raise OpportunityNotFound(f"no opportunity with id {opportunity_id!r}")

    # -- the rules ----------------------------------------------------------------

    def _partner_stems(self) -> dict[str, str]:
        """Every Partner hub under `Work/Partners`, by lower-cased stem and name."""
        stems = {}
        for entry in self._api.vault.entries():
            if entry["frontmatter"].get("type") != "Partner" or "Partners" not in Path(entry["path"]).parts:
                continue
            stems.setdefault(entry["stem"].lower(), entry["stem"])
            name = _text(entry["frontmatter"].get("name"))
            if name:
                stems.setdefault(name.lower(), entry["stem"])
        return stems

    def _validated_fields(self, fields: dict) -> dict:
        unknown = sorted(set(fields) - set(EDITABLE))
        if unknown:
            raise OpportunityError(f"these fields cannot be set: {', '.join(unknown)}")
        clean = {}
        for key, value in fields.items():
            if key in _LIST_FIELDS:
                items = value if isinstance(value, list) else ([value] if _text(value) else [])
                items = [_text(v) for v in items if _text(v)]
                if key == "product":
                    for item in items:
                        if item not in ENUMS["product"]:
                            raise OpportunityError(f"product {item!r} is not one of {', '.join(ENUMS['product'])}")
                if key == "partner":
                    known = self._partner_stems()
                    resolved = []
                    for item in items:
                        stem = known.get(item.strip("[]").lower())
                        if stem is None:
                            raise OpportunityError(f"partner {item!r} is not a note under Work/Partners")
                        resolved.append(stem)
                    items = resolved
                clean[key] = list(dict.fromkeys(items))
            elif key == "expected_monthly_usd":
                clean[key] = "" if _text(value) == "" else _usd(value, "expected_monthly_usd")
            else:
                text = _text(value)
                if key in ENUMS and text not in ENUMS[key]:
                    raise OpportunityError(f"{key} {text!r} is not one of {', '.join(ENUMS[key])}")
                if key == "consumption_start" and text and not _MONTH.match(text):
                    raise OpportunityError(f"consumption_start must be YYYY-MM, not {text!r}")
                clean[key] = text
        return clean

    @staticmethod
    def _check_rules(merged: dict, touched: set[str], plan: list[dict] | None) -> None:
        """The Template's cross-field rules, for the rules a write touches: a note
        written before a rule existed is not refused an unrelated edit."""
        status, stage = _text(merged.get("status")), _text(merged.get("stage"))
        route, draws = _text(merged.get("route")), _text(merged.get("draws_against"))
        if touched & {"status", "stage"}:
            if status in _CLOSED_STATUSES and stage != "Closed":
                raise OpportunityError(f"status {status} requires stage Closed")
            if stage == "Closed" and status not in _CLOSED_STATUSES:
                raise OpportunityError("stage Closed requires status Won or Lost")
        if touched & {"route", "draws_against"}:
            if route == "csp" and draws:
                raise OpportunityError("route csp draws against nothing: draws_against must be empty")
            if draws and route not in _DRAWING_ROUTES:
                raise OpportunityError(f"draws_against needs route {', '.join(_DRAWING_ROUTES)}")
        if plan:
            if touched & {"expected_monthly_usd", "plan"} and merged.get("expected_monthly_usd") != plan[-1]["usd"]:
                raise OpportunityError("expected_monthly_usd is the Consumption Plan's last month "
                                       f"({plan[-1]['usd']}), not {merged.get('expected_monthly_usd')!r}")
            start = _text(merged.get("consumption_start"))
            if touched & {"consumption_start", "plan"} and start and start > plan[0]["month"]:
                raise OpportunityError(f"consumption_start {start} is after the plan's first month {plan[0]['month']}")

    @staticmethod
    def _plan_derived(clean: dict, plan: list[dict]) -> dict:
        """The plan's last month is the steady state, `expected_monthly_usd`."""
        derived = dict(clean)
        if plan:
            derived.setdefault("expected_monthly_usd", plan[-1]["usd"])
        return derived

    # -- writing --------------------------------------------------------------

    @staticmethod
    def _checked_title(title: str) -> str:
        text = _text(title)
        if not text:
            raise OpportunityError("title is required")
        if text != str(title).strip():
            raise OpportunityError("title must be a single line with single spaces")
        if _FILENAME_INVALID.search(text) or text.endswith((".", " ")) or text in (".", ".."):
            raise OpportunityError(f"title {text!r} cannot be a file name, and the Template "
                                   'names the file after the title (no \\ / : * ? " < > |)')
        return text

    def create(self, owner_stem: str, title: str, fields: dict, plan: list[dict]) -> dict:
        hubs = self._hubs()
        owner = self._hub(owner_stem, hubs)
        customer = self._customer_of(owner, hubs)
        if customer is None:
            raise OpportunityNotFound(f"{owner_stem!r} sits in a Customer folder with no hub note")
        affiliate = None if owner is customer else owner
        title = self._checked_title(title)

        taken = {path.stem.lower() for path in self._opportunity_paths(owner)}
        folder = owner["path"].parent / "Opportunities" / title
        if title.lower() in taken or _exists(folder):
            raise OpportunityError(f"{owner['name']} already has an opportunity titled {title!r}")

        rows = validated_plan(plan or [])
        clean = self._plan_derived(self._validated_fields(dict(fields or {})), rows)
        if rows and not clean.get("consumption_start"):
            clean["consumption_start"] = rows[0]["month"]
        today = _today()
        values = {key: (list(value) if isinstance(value, list) else value) for key, value in DEFAULTS.items()}
        values.update(clean)
        values.update({
            "id": str(uuid.uuid4()), "title": title, "customer": owner["stem"],
            "created": today, "updated": today,
            "tags": list(dict.fromkeys([*DEFAULTS["tags"], owner["tag"]])),
        })
        self._check_rules(values, set(clean) | {"plan", "status", "stage", "route", "draws_against"}, rows)
        frontmatter = {key: values[key] for key in KEY_ORDER}

        related = [f"- [[{owner['stem']}]]"] + [f"- [[{stem}]]" for stem in frontmatter["partner"]]
        children_index = [f"- [[{title}-{child['suffix']}|{child['label']}]]" for child in CHILDREN]
        contents = {
            PLAN_SECTION: plan_table(rows),
            "Related": "\n".join(related),
            "History & Captures": "\n".join(children_index),
        }
        body = "\n" + "\n".join(f"## {name}\n\n{contents.get(name, '')}\n" for name in SECTIONS)

        note = folder / f"{title}.md"
        _write_text(note, _frontmatter_text(frontmatter) + body)
        for child in CHILDREN:
            child_frontmatter = {
                "type": child["type"], "tags": [child["tag"]],
                "name": f"{title} {child['label']}", "parent": f"[[{title}]]",
            }
            _write_text(folder / f"{title}-{child['suffix']}.md",
                        _frontmatter_text(child_frontmatter) + f"\n# {title}\n\n")
        _link_into_section(owner["path"], LINK_BACK_SECTION, f"[[{title}]]")
        return self._describe(note, frontmatter, customer, affiliate)

    def update(self, opportunity_id: str, fields: dict, plan: list[dict] | None = None) -> dict:
        path, frontmatter, customer, affiliate = self._find(opportunity_id)
        clean = self._validated_fields(dict(fields or {}))
        rows = validated_plan(plan) if plan is not None else None
        current_plan = parse_plan(self._api.vault.read_section(path, PLAN_SECTION))
        effective_plan = rows if rows is not None else current_plan
        if rows:
            clean = self._plan_derived(clean, rows)
            if not _text(clean.get("consumption_start", frontmatter.get("consumption_start"))):
                clean["consumption_start"] = rows[0]["month"]

        def as_stored(key, value):
            if key == "expected_monthly_usd":
                text = _text(value)
                return int(text) if text.isdigit() else text
            if key in _LIST_FIELDS:
                return list(value) if isinstance(value, list) else ([_text(value)] if _text(value) else [])
            return _text(value)

        changed = {key: value for key, value in clean.items()
                   if as_stored(key, frontmatter.get(key, DEFAULTS.get(key))) != value}
        plan_changed = rows is not None and rows != current_plan
        merged = {key: as_stored(key, frontmatter.get(key, DEFAULTS.get(key))) for key in EDITABLE}
        merged.update(clean)
        touched = set(changed) | ({"plan"} if plan_changed else set())
        self._check_rules(merged, touched, effective_plan)
        if not changed and not plan_changed:
            return self._describe(path, frontmatter, customer, affiliate)

        # A note written against Template v2 is brought to v3 by its first edit:
        # the new keys at their defaults and an empty plan table, so no bulk
        # migration ever has to touch the vault.
        upgrade = {key: DEFAULTS[key] for key in ("billing_profile", "consumption_start") if key not in frontmatter}
        text = _read_text(path)
        text = self._with_frontmatter(text, {**upgrade, **changed, "updated": _today()})
        if plan_changed or _section_bounds(text.split("\n"), PLAN_SECTION) is None:
            text = _with_section(text, PLAN_SECTION, plan_table(effective_plan), after="Summary")
        _write_text(path, text)
        self._log(path, frontmatter, changed, rows if plan_changed else None)

        new_frontmatter, _ = self._api.vault.read_note(path)
        return self._describe(path, new_frontmatter, customer, affiliate)

    @staticmethod
    def _with_frontmatter(text: str, values: dict) -> str:
        """`text` with these frontmatter keys set, every other line left exactly
        as it was. A key the note lacks (a v2 note has no `billing_profile`) goes
        where the Template's key order puts it."""
        return with_frontmatter(text, values, KEY_ORDER)

    def _log(self, path: Path, before: dict, changed: dict, plan: list[dict] | None) -> None:
        parts = [f"{key} {_format_change(before.get(key))} -> {_format_change(value)}" for key, value in changed.items()]
        if plan is not None:
            parts.append(f"Consumption Plan {plan[0]['month']} to {plan[-1]['month']}, "
                         f"{plan[-1]['usd']} USD a month at the end" if plan else "Consumption Plan cleared")
        history = path.parent / f"{path.stem}-history.md"
        if _exists(history):
            text = _read_text(history)
        else:
            title = _text(before.get("title")) or path.stem
            text = _frontmatter_text({"type": "History", "tags": ["kind/history"],
                                      "name": f"{title} History", "parent": f"[[{path.stem}]]"}) + f"\n# {title}\n\n"
        _write_text(history, _with_line_appended(text, HISTORY_SECTION,
                                                 f"- {_today()}: updated {'; '.join(parts)} (entities.opportunities)"))


def _format_change(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    text = _text(value)
    return text if text else '""'
