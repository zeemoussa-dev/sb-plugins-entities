"""A Customer's signed Azure commitment (MACC, EA commitment, prepayment), held
as flat `macc_*` frontmatter on its hub note.

The note is the single source of truth (operator, 2026-10-17): Obsidian's
Properties pane shows and edits these keys, and another plugin reads and writes
them through `entities.customers` rather than keeping its own copy. Only these
keys are ever touched; every other line of the note stays as it was.
"""
from __future__ import annotations

import re
from datetime import date

from .opportunities import OpportunityError, _read_text, _text, _write_text, with_frontmatter

TYPES = ["MACC", "EA commitment", "Azure Prepayment", "Other"]
# How a parent's affiliates relate to its commitment (operator, 2026-10-18): "roll up"
# -- they sign none of their own, so their consumption burns the parent's (DGE) -- or
# "own" -- each signed its own, so only the parent's own enrollments burn it (Mubadala).
AFFILIATES = ["roll up", "own"]
# Field of the commitment -> its frontmatter key, in the order they are written.
KEYS = {
    "type": "macc_type",
    "amount": "macc_amount",
    "currency": "macc_currency",
    "start": "macc_start",
    "end": "macc_end",
    "note": "macc_note",
    "include_marketplace": "macc_includes_marketplace",
    "subtract_credits": "macc_subtracts_credits",
    "affiliates": "macc_affiliates",
}
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _date(value, field: str) -> str:
    text = _text(value)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    raise OpportunityError(f"{field} must be a date, YYYY-MM-DD, not {value!r}")


def _flag(value, field: str) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    raise OpportunityError(f"{field} must be true or false")


def _number(value):
    """An int when the amount is whole, so the Properties pane shows 5000000, not 5000000.0."""
    return int(value) if float(value).is_integer() else float(value)


def validated(commitment: dict) -> dict:
    if not isinstance(commitment, dict):
        raise OpportunityError("a commitment is a dict, or None to clear it")
    unknown = sorted(set(commitment) - set(KEYS))
    if unknown:
        raise OpportunityError(f"these commitment fields are not known: {', '.join(unknown)}")
    kind = _text(commitment.get("type"))
    if kind not in TYPES:
        raise OpportunityError(f"type must be one of {', '.join(TYPES)}, not {kind!r}")
    amount = commitment.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        raise OpportunityError(f"amount must be a non-negative number, not {amount!r}")
    currency = _text(commitment.get("currency")) or "USD"
    if not _CURRENCY.match(currency):
        raise OpportunityError(f"currency must be a three-letter code such as USD, not {currency!r}")
    affiliates = _text(commitment.get("affiliates")) or AFFILIATES[0]
    if affiliates not in AFFILIATES:
        raise OpportunityError(f"affiliates must be one of {', '.join(AFFILIATES)}, not {affiliates!r}")
    start, end = _date(commitment.get("start"), "start"), _date(commitment.get("end"), "end")
    if end < start:
        raise OpportunityError(f"end {end} is before start {start}")
    return {
        "type": kind, "amount": _number(amount), "currency": currency, "start": start, "end": end,
        "note": _text(commitment.get("note")),
        "include_marketplace": _flag(commitment.get("include_marketplace"), "include_marketplace"),
        "subtract_credits": _flag(commitment.get("subtract_credits"), "subtract_credits"),
        "affiliates": affiliates,
    }


def from_frontmatter(frontmatter: dict) -> dict | None:
    """The commitment a note holds, or None when it holds none. Read leniently:
    a value an operator typed by hand in Obsidian is returned as it reads, never
    refused, so one odd field does not hide the whole commitment."""
    if not any(key in frontmatter for key in KEYS.values()):
        return None

    def flag(key):
        return _text(frontmatter.get(key)).lower() != "false"

    amount = _text(frontmatter.get(KEYS["amount"])).replace(",", "")
    return {
        "type": _text(frontmatter.get(KEYS["type"])),
        "amount": _number(amount) if _NUMBER.match(amount) else None,
        "currency": _text(frontmatter.get(KEYS["currency"])) or "USD",
        "start": _text(frontmatter.get(KEYS["start"])),
        "end": _text(frontmatter.get(KEYS["end"])),
        "note": _text(frontmatter.get(KEYS["note"])),
        "include_marketplace": flag(KEYS["include_marketplace"]),
        "subtract_credits": flag(KEYS["subtract_credits"]),
        # Anything typed by hand other than "own" reads as the default.
        "affiliates": "own" if _text(frontmatter.get(KEYS["affiliates"])).lower() == "own" else AFFILIATES[0],
    }


def write(path, commitment: dict | None) -> None:
    values = {} if commitment is None else {KEYS[field]: value for field, value in validated(commitment).items()}
    text = _read_text(path)
    new_text = with_frontmatter(text, values, remove=() if commitment is not None else tuple(KEYS.values()))
    if new_text != text:
        _write_text(path, new_text)
