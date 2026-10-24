"""Customers & Partners as the operator browses them: every hub note, and one
hub's data gathered in one place -- its own fields and sections, its
Opportunities, People, activity, its Captures, and what other plugins know of it.

Two things on a hub are the operator's to write from here (operator, 2026-10-17):
the hub's `## Personal Notes`, and the Captures note's own `## Notes`. Every
other section is Hermes' and is only shown. The Plugin API has no vault write,
so writes are this plugin's own, as `opportunities.py`'s are: only the named
section changes, every path comes from a hub found on disk, never from a caller.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import capture_writer, commitment
from .opportunities import (
    Opportunities, OpportunityError, OpportunityNotFound, _exists, _frontmatter_text, _long,
    _notes_in_own_folders, _read_text, _section_bounds, _tag_slug, _text,
    _with_section, _write_text,
)

KINDS = {"customer": ("Customers", "Customer"), "partner": ("Partners", "Partner")}
PERSONAL_NOTES = "Personal Notes"
CAPTURE_NOTES = "Notes"
CAPTURED = "Captured"
ACTIVITY_LIMIT = 40
COST_SERVICE = "azure-cost-manager.portfolio"

_SECTION_HEADING = re.compile(r"^## (.+?)\s*$")
_FRONTMATTER_LINE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s?(.*)$")
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
# Enough of a Thread note to hold its frontmatter; the messages follow it.
_THREAD_HEAD_BYTES = 8192


class AccountConflict(OpportunityError):
    """The section changed on disk since the page loaded it (Obsidian, Hermes)."""


def _sections(body: str) -> tuple[str, list[dict]]:
    """(text before the first `## `, [{name, text}]) of a note body."""
    intro, sections, current = [], [], None
    for line in body.split("\n"):
        match = _SECTION_HEADING.match(line)
        if match:
            current = {"name": match.group(1), "lines": []}
            sections.append(current)
        elif current is None:
            intro.append(line)
        else:
            current["lines"].append(line)
    return "\n".join(intro).strip(), [{"name": s["name"], "text": "\n".join(s["lines"]).strip()} for s in sections]


def _section_text(text: str, name: str) -> str | None:
    lines = text.split("\n")
    bounds = _section_bounds(lines, name)
    return None if bounds is None else "\n".join(lines[bounds[0] + 1:bounds[1]]).strip()


def _head_frontmatter(path: Path) -> dict:
    """The frontmatter of a note read off disk, for notes the index leaves out
    (Threads, by design). Only strings and flow lists, as the vault writes them."""
    try:
        with open(_long(path), encoding="utf-8", errors="replace") as handle:
            head = handle.read(_THREAD_HEAD_BYTES)
    except OSError:
        return {}
    if not head.startswith("---\n"):
        return {}
    end = head.find("\n---", 4)
    values = {}
    for line in head[4:end if end != -1 else len(head)].split("\n"):
        match = _FRONTMATTER_LINE.match(line)
        if not match:
            continue
        raw = match.group(2).strip()
        if raw.startswith("["):
            values[match.group(1)] = [v.replace('\\"', '"') for v in _QUOTED.findall(raw)]
        else:
            values[match.group(1)] = raw[1:-1].replace('\\"', '"') if raw.startswith('"') and raw.endswith('"') else raw
    return values


def _listed(value) -> list[str]:
    if isinstance(value, list):
        return [_text(v) for v in value if _text(v)]
    return [_text(value)] if _text(value) else []


class Accounts:
    def __init__(self, api) -> None:
        self._api = api

    # -- finding hubs -----------------------------------------------------------

    def _work_folder(self) -> Path | None:
        return Opportunities(self._api)._work_folder()

    def _hubs(self, kind: str) -> list[dict]:
        """Every hub of one kind, read off the disk: `<Kind>/<H>/<H>.md`, and its
        affiliates at `<H>/Affiliates/<A>/<A>.md`, as deep as they nest (a Partner's
        affiliate has its own). The index lags a hub made a moment ago."""
        folder_name, note_type = KINDS[kind]
        work = self._work_folder()
        if work is None:
            return []
        hubs: list[dict] = []

        def walk(folder: Path, parent: dict | None) -> None:
            for path in _notes_in_own_folders(folder):
                frontmatter, body = self._api.vault.read_note(path)
                if _text(frontmatter.get("type")) != note_type:
                    continue
                tags = _listed(frontmatter.get("tags"))
                prefix = f"{kind}/"
                hub = {
                    "kind": kind,
                    "name": _text(frontmatter.get("name")) or path.stem,
                    "stem": path.stem,
                    "tag": next((t for t in tags if t.startswith(prefix)), f"{prefix}{_tag_slug(path.stem)}"),
                    "path": path,
                    "parent": parent["stem"] if parent else None,
                    "frontmatter": frontmatter,
                    "body": body,
                }
                hubs.append(hub)
                walk(path.parent / "Affiliates", hub)

        walk(work / folder_name, None)
        return hubs

    def _hub(self, kind: str, stem: str) -> tuple[dict, list[dict]]:
        if kind not in KINDS:
            raise OpportunityNotFound(f"kind is customer or partner, not {kind!r}")
        hubs = self._hubs(kind)
        found = [hub for hub in hubs if hub["stem"] == _text(stem)]
        if not found:
            raise OpportunityNotFound(f"no {kind} named {stem!r}")
        if len(found) > 1:
            raise OpportunityError(f"more than one {kind} is named {stem!r}")
        return found[0], hubs

    # -- the list ---------------------------------------------------------------

    def _people_by_hub(self, hubs: list[dict]) -> dict[str, list[dict]]:
        """Person notes in a hub's own `People/` folder, or carrying its tag."""
        by_folder = {hub["path"].parent / "People": hub["stem"] for hub in hubs}
        by_tag = {hub["tag"]: hub["stem"] for hub in hubs}
        people: dict[str, dict[str, dict]] = {hub["stem"]: {} for hub in hubs}
        for entry in self._api.vault.entries():
            if entry["frontmatter"].get("type") != "Person":
                continue
            path = Path(entry["path"])
            owners = {by_folder[path.parent]} if path.parent in by_folder else set()
            owners |= {by_tag[tag] for tag in entry["tags"] if tag in by_tag}
            frontmatter = entry["frontmatter"]
            person = {
                "stem": entry["stem"],
                "name": _text(frontmatter.get("name")) or entry["stem"],
                "email": _text(frontmatter.get("email")),
                "role": _text(frontmatter.get("role")),
                "department": _text(frontmatter.get("department")),
            }
            for owner in owners:
                people[owner][entry["stem"]] = person
        return {stem: sorted(found.values(), key=lambda p: p["name"].lower()) for stem, found in people.items()}

    def list(self) -> dict:
        result = {}
        for kind in KINDS:
            hubs = self._hubs(kind)
            people = self._people_by_hub(hubs)
            rows = []
            for hub in hubs:
                frontmatter = hub["frontmatter"]
                rows.append({
                    "kind": kind,
                    "name": hub["name"],
                    "stem": hub["stem"],
                    "tag": hub["tag"],
                    "parent": hub["parent"],
                    "domain": _text(frontmatter.get("domain")),
                    "description": _text(frontmatter.get("description")),
                    "affiliates": sum(1 for other in hubs if other["parent"] == hub["stem"]),
                    "opportunities": len(_notes_in_own_folders(hub["path"].parent / "Opportunities")),
                    "people": len(people.get(hub["stem"], [])),
                    "has_commitment": commitment.from_frontmatter(frontmatter) is not None,
                })
            result[f"{kind}s"] = rows
        return result

    # -- one hub ----------------------------------------------------------------

    def _opportunities(self, hub: dict) -> list[dict]:
        """A hub's own pipeline; a Partner's also holds every Customer opportunity naming it."""
        service = Opportunities(self._api)
        try:
            found = service.list_for_customer(hub["stem"])
            if hub["kind"] == "partner":
                for customer in service.customers():
                    found += [o for o in service.list_for_customer(customer["stem"]) if hub["stem"] in o["partner"]]
            return found
        except OpportunityError:
            # A hub the service cannot place (its parent folder has no hub note)
            # has no pipeline to show, which is not this page's failure.
            return []

    def _activity(self, hub: dict) -> list[dict]:
        items = []
        for entry in self._api.vault.entries():
            frontmatter = entry["frontmatter"]
            if frontmatter.get("type") != "Meeting" or hub["tag"] not in entry["tags"]:
                continue
            items.append({"kind": "meeting", "stem": entry["stem"],
                          "title": _text(frontmatter.get("title")) or entry["stem"],
                          "date": _text(frontmatter.get("start")) or _text(frontmatter.get("created"))})
        # Threads are left out of the vault index on purpose, so read off disk.
        work = self._work_folder()
        for path in _notes_in_own_folders(work / "Threads") if work else []:
            frontmatter = _head_frontmatter(path)
            if hub["tag"] not in _listed(frontmatter.get("tags")):
                continue
            items.append({"kind": "thread", "stem": path.stem,
                          "title": _text(frontmatter.get("thread_name")) or path.stem,
                          "date": _text(frontmatter.get("last_message_at")) or _text(frontmatter.get("created"))})
        items.sort(key=lambda item: item["date"], reverse=True)
        return items[:ACTIVITY_LIMIT]

    def _captures_path(self, hub: dict) -> Path:
        return hub["path"].parent / f"{hub['stem']}-captures.md"

    def _captures(self, hub: dict) -> dict:
        # `stem` is what the vault editor opens: the page edits the whole note
        # there, since real Captures notes keep their content in sections of
        # their own, not only under `## Notes`.
        path = self._captures_path(hub)
        if not _exists(path):
            return {"exists": False, "stem": path.stem, "body": ""}
        _, body = self._api.vault.read_note(path)
        return {"exists": True, "stem": path.stem, "body": body.strip()}

    def create_captures_note(self, kind: str, stem: str) -> dict:
        """The hub's Captures note, made when it has none, so the editor has a note to open."""
        hub, _ = self._hub(kind, stem)
        self._ensure_captures(hub)
        return self._captures(hub)

    def _news(self, hub: dict) -> str | None:
        path = hub["path"].parent / f"{hub['stem']}-news.md"
        if not _exists(path):
            return None
        _, body = self._api.vault.read_note(path)
        return body.strip() or None

    def cost(self, kind: str, stem: str) -> dict:
        """What Azure Cost Manager knows of this customer, through its service. Not
        installed, too old, or failing all read as "nothing to show". Asked apart
        from `detail`: the service computes the customer's burn (seconds, on a real
        install) and the rest of the page should not wait for it."""
        hub, _ = self._hub(kind, stem)
        service = self._api.get_service(COST_SERVICE)
        if service is None or not hasattr(service, "for_entity"):
            return {"available": False, "row": None}
        try:
            return {"available": True, "row": service.for_entity(hub["stem"])}
        except Exception as exc:  # another plugin's failure stays its own
            return {"available": True, "row": None, "error": str(exc)}

    def detail(self, kind: str, stem: str) -> dict:
        hub, hubs = self._hub(kind, stem)
        frontmatter = hub["frontmatter"]
        intro, sections = _sections(hub["body"])
        lineage, parent = [], hub["parent"]
        while parent:
            above = next(h for h in hubs if h["stem"] == parent)
            lineage.insert(0, {"name": above["name"], "stem": above["stem"]})
            parent = above["parent"]
        return {
            "kind": kind,
            "name": hub["name"],
            "stem": hub["stem"],
            "tag": hub["tag"],
            "domain": _text(frontmatter.get("domain")),
            "description": _text(frontmatter.get("description")),
            "aliases": _listed(frontmatter.get("aliases")),
            "tags": _listed(frontmatter.get("tags")),
            "lineage": lineage,
            "affiliates": [{"name": h["name"], "stem": h["stem"]} for h in hubs if h["parent"] == hub["stem"]],
            # A Partner's hub may carry one too, when Azure Cost Manager links a customer to it.
            "commitment": commitment.from_frontmatter(frontmatter),
            "intro": intro,
            "sections": sections,
            "personal_notes": next((s["text"] for s in sections if s["name"] == PERSONAL_NOTES), ""),
            "captures": self._captures(hub),
            "news": self._news(hub),
            "opportunities": self._opportunities(hub),
            "people": self._people_by_hub([hub])[hub["stem"]],
            "activity": self._activity(hub),
        }

    # -- writing ----------------------------------------------------------------

    def create_customer(self, name: str, aliases: list[str] | None = None) -> dict:
        return Opportunities(self._api).create_customer(name, aliases)

    @staticmethod
    def _replace_section(path: Path, name: str, text: str, previous: str, *, before: str | None = None) -> None:
        """`## <name>` holding `text`, refused when it no longer holds `previous`."""
        current = _read_text(path)
        if _text_block(_section_text(current, name)) != _text_block(previous):
            raise AccountConflict(f"{name} changed since this page loaded it; reload to see the change first")
        _write_if_changed(path, current, _with_section_before(current, name, _text_block(text), before))

    def set_personal_notes(self, kind: str, stem: str, text: str, previous: str) -> str:
        hub, _ = self._hub(kind, stem)
        self._replace_section(hub["path"], PERSONAL_NOTES, text, previous, before="Actions")
        return _section_text(_read_text(hub["path"]), PERSONAL_NOTES) or ""

    def _ensure_captures(self, hub: dict) -> Path:
        """The hub's Captures note, made as the Template makes its child when the hub has none."""
        path = self._captures_path(hub)
        if not _exists(path):
            frontmatter = {"type": "Captures", "name": f"{hub['name']} Captures",
                           "parent": f"[[{hub['stem']}]]", "tags": [hub["tag"], "kind/captures"]}
            body = f"\n# {hub['name']}\n\n## {CAPTURE_NOTES}\n\n## {CAPTURED}\n"
            _write_if_changed(path, "", _frontmatter_text(frontmatter) + body)
        return path

    def add_capture(self, kind: str, stem: str, title: str, text: str, author: str) -> dict:
        """A capture is a section of its own (operator, 2026-10-24): `## <date> — <title>`,
        then who added it and when, then the text -- the shape the operator's own
        captures already have. Newest first: it goes above every other section."""
        hub, _ = self._hub(kind, stem)
        body = _text_block(text)
        if not body:
            raise OpportunityError("a capture needs some text")
        added = {"tidied": False, "note": ""}
        if not _text(title):
            # Typed in place with no title: Compass titles it and fixes the typing.
            composed = capture_writer.compose(self._api, body)
            title, body = composed["title"], _text_block(composed["text"]) or body
            added.update(tidied=composed["tidied"], note=composed["note"])
        title = _text(title).lstrip("#").strip() or capture_writer.FALLBACK_TITLE
        now = datetime.now()
        heading = f"## {now.date().isoformat()} — {title}"
        signed = f"*Added by {_text(author) or 'someone'} on {now.strftime('%Y-%m-%d %H:%M')}*"
        block = [heading, "", signed, "", *body.split("\n"), ""]
        path = self._ensure_captures(hub)
        lines = _read_text(path).split("\n")
        first_section = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
        if first_section is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", *block]
        else:
            lines[first_section:first_section] = block
        _write_if_changed(path, None, "\n".join(lines))
        return {**self._captures(hub), "added": {"title": title, **added}}


def _text_block(text) -> str:
    """Multi-line text as stored: no trailing spaces, Windows line ends folded, trimmed."""
    return "\n".join(line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")).strip()


def _with_section_before(text: str, name: str, content: str, before: str | None) -> str:
    """`_with_section`, but a missing section goes in front of `before` when the
    note has that one -- Notes belong above the automated Captured."""
    lines = text.split("\n")
    anchor = _section_bounds(lines, before) if before else None
    if _section_bounds(lines, name) is not None or anchor is None:
        return _with_section(text, name, content)
    block = [f"## {name}", "", *([*content.split("\n"), ""] if content else [])]
    lines[anchor[0]:anchor[0]] = block
    return "\n".join(lines)


def _write_if_changed(path: Path, before: str | None, after: str) -> None:
    if before != after:
        _write_text(path, after)
