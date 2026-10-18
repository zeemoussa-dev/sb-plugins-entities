"""A Customer's (or affiliate's, or Partner's) Insight terms: the Core42 Insight
plugin's revenue terms, kept in a note of their own beside the hub,
`<hub folder>/<stem> - Insight.md`.

Not on the hub (operator, 2026-10-18): terms are a list of maps, and the
framework's frontmatter parser and the shared Hermes engine read frontmatter line
by line and rewrite all of it -- a nested block on the hub would be wiped by the
next Skill write. Here the frontmatter is flat and the data is one fenced json
block in the body, which nothing re-serialises. No Skill writes this note.

Entities checks shape (dates are dates, numbers are numbers); Insight checks
meaning (overlaps, percent range). Unknown term keys and models are kept.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from .opportunities import OpportunityError, _exists, _frontmatter_text, _long, _read_text, _text, _write_text

DATA_SECTION = "Data"
_DATA_BLOCK = re.compile(r"^## Data\s*\n+```json\s*\n(.*?)\n```", re.M | re.S)
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TERM_DATES = ("start", "end")
_TERM_NUMBERS = ("percent", "amount")
_TERM_FLAGS = ("include_marketplace", "subtract_credits")


def note_path(hub_path: Path) -> Path:
    return hub_path.parent / f"{hub_path.stem} - Insight.md"


def _day(value, where: str) -> str:
    text = _text(value)
    try:
        if _DAY.match(text):
            return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    raise OpportunityError(f"{where} must be a date, YYYY-MM-DD, not {value!r}")


def _number(value, where: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpportunityError(f"{where} must be a number, not {value!r}")
    return int(value) if float(value).is_integer() else float(value)


def validated(value: dict) -> dict:
    if not isinstance(value, dict):
        raise OpportunityError("insight is a dict {terms, note}, or None to remove it")
    unknown = sorted(set(value) - {"terms", "note"})
    if unknown:
        raise OpportunityError(f"these insight fields are not known: {', '.join(unknown)}")
    terms = value.get("terms") or []
    if not isinstance(terms, list):
        raise OpportunityError("terms must be a list")
    clean_terms = []
    for index, term in enumerate(terms, 1):
        where = f"term {index}"
        if not isinstance(term, dict):
            raise OpportunityError(f"{where} must be a map")
        model = _text(term.get("model"))
        if not model:
            raise OpportunityError(f"{where} needs a model")
        clean = dict(term)
        clean["model"] = model
        clean["start"] = _day(term.get("start"), f"{where} start")
        if term.get("end") not in (None, ""):
            clean["end"] = _day(term["end"], f"{where} end")
            if clean["end"] < clean["start"]:
                raise OpportunityError(f"{where} ends {clean['end']}, before it starts {clean['start']}")
        else:
            clean.pop("end", None)
        for key in _TERM_NUMBERS:
            if key in term and term[key] is not None:
                clean[key] = _number(term[key], f"{where} {key}")
        for key in _TERM_FLAGS:
            if key in term and not isinstance(term[key], bool):
                raise OpportunityError(f"{where} {key} must be true or false")
        clean_terms.append(clean)
    note = value.get("note")
    if note is not None and not isinstance(note, str):
        raise OpportunityError("note must be text")
    return {"terms": clean_terms, "note": note or ""}


def read(hub_path: Path) -> dict | None:
    path = note_path(hub_path)
    if not _exists(path):
        return None
    match = _DATA_BLOCK.search(_read_text(path))
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        # Refused rather than read as None, or the next save would overwrite a
        # hand edit that only needed a comma.
        raise OpportunityError(f"{path.name} holds JSON that does not parse: {exc}") from exc
    if not isinstance(data, dict):
        raise OpportunityError(f"{path.name} holds JSON that is not a map")
    return {"terms": data.get("terms") or [], "note": data.get("note") or ""}


def _cell(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).replace("|", "\\|")


def _readable(data: dict) -> str:
    """A table for reading in Obsidian. Generated from the json on every save; the json is what is read."""
    columns = ["model", "start", "end", "percent", "amount", "include_marketplace", "subtract_credits"]
    lines = ["## Terms", ""]
    if data["terms"]:
        lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
        lines += ["| " + " | ".join(_cell(term.get(c)) for c in columns) + " |" for term in data["terms"]]
    else:
        lines.append("No terms.")
    # An upfront term paid in instalments (Insight 0.4.0): one list per term that has them.
    for index, term in enumerate(data["terms"], 1):
        payments = term.get("payments")
        if not isinstance(payments, list) or not payments:
            continue
        lines += ["", f"Payments for term {index} ({_cell(term.get('model'))} from {_cell(term.get('start'))}):", ""]
        for payment in payments:
            if isinstance(payment, dict):
                note = f" -- {payment['note']}" if payment.get("note") else ""
                lines.append(f"- {_cell(payment.get('date'))}: {_cell(payment.get('amount'))}{note}")
    if data["note"]:
        lines += ["", "## Note", "", data["note"]]
    return "\n".join(lines)


def write(hub_path: Path, hub_name: str, value: dict | None) -> None:
    path = note_path(hub_path)
    if value is None:
        if _exists(path):
            os.remove(_long(path))
        return
    data = validated(value)
    frontmatter = {"type": "Insight", "name": f"{hub_name} Insight", "parent": f"[[{hub_path.stem}]]",
                   "tags": ["kind/insight"]}
    body = (f"\n# {hub_name} — Insight\n\n"
            "Revenue terms for the Core42 Insight plugin, written by Entities. "
            "Edit them in Insight's Settings; the json block below is what is read, and the "
            "tables after it are regenerated from it on every save.\n\n"
            f"## {DATA_SECTION}\n\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n\n"
            f"{_readable(data)}\n")
    _write_text(path, _frontmatter_text(frontmatter) + body)
