"""A new capture's title and its typing fixed, by Compass (operator, 2026-10-24:
"Add new in place and then when I finish typing you add the title and finetune
the text same as the Vault").

"Fine-tune" means what the vault's "Tidy the typing" means, and nothing more:
spelling, capitalisation, doubled words, missing full stops. A capture is the
operator's own account of a conversation, and agents read these notes, so a
model that rephrased a sentence or renamed a [[link]] would be worse than a
typo. As in the vault, the prompt asks for that and the checks below enforce
it: a reply that moved a link, an address or a line break, or grew or shrank
the text, is not used -- the capture is saved as typed instead.

Compass is reached through `api.llm` (optional under Plugin API 12). Not
configured, failing or refused: the capture is still saved, as typed, with a
plain title -- what the operator wrote is never lost to a model's mood.
"""
from __future__ import annotations

import re

FALLBACK_TITLE = "Capture"
MAX_CHARACTERS = 12_000
_TITLE_WORDS = 8

_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_URL = re.compile(r"https?://\S+")
_TITLE_LINE = re.compile(r"^\s*TITLE:\s*(.+?)\s*$", re.IGNORECASE)

_INSTRUCTION = f"""You file a note an account manager just typed about a customer or partner.

Reply in exactly this shape and nothing else:
TITLE: <a short title for the note, at most {_TITLE_WORDS} words, no quotes, no date>

<the note with its typing mistakes corrected>

For the corrected note, fix ONLY:
- misspelled words
- obviously wrong capitalisation of ordinary words
- doubled words, and missing or doubled spaces
- missing sentence-ending punctuation

Change NOTHING else. Keep every one of these exactly as it is, character for character:
- text inside [[double brackets]] -- these are links and renaming one breaks it
- lists, their order, their markers and their indentation
- URLs, file names, code, and anything inside backticks
- tags, dates, numbers, names of people, companies and products
- line breaks and blank lines

Never add a sentence. Never remove one. Never rephrase one. Never translate."""


def _title_from(text: str) -> str:
    title = re.sub(r"[#*_`\[\]\"“”]", "", text).strip(" .:-—'")
    words = title.split()
    return " ".join(words[:_TITLE_WORDS]) if words else ""


def _structure_kept(original: str, cleaned: str) -> bool:
    if not cleaned.strip():
        return False
    if _WIKILINK.findall(original) != _WIKILINK.findall(cleaned):
        return False
    if _URL.findall(original) != _URL.findall(cleaned):
        return False
    if cleaned.count("\n") != original.count("\n"):
        return False
    return abs(len(cleaned) - len(original)) <= max(80, len(original) * 0.15)


def _unwrap(answer: str) -> str:
    lines = (answer or "").strip("\n").splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return "\n".join(lines)


def compose(api, text: str) -> dict:
    """`{title, text, tidied, note}` for a capture typed as `text`. `tidied` says
    whether Compass's version was used; `note` says why not, when it was not."""
    llm = getattr(api, "llm", None)
    if llm is None or not getattr(llm, "available", lambda: False)():
        return {"title": FALLBACK_TITLE, "text": text, "tidied": False, "note": "Compass is not set up on this install."}
    if len(text) > MAX_CHARACTERS:
        return {"title": FALLBACK_TITLE, "text": text, "tidied": False, "note": "Too long to tidy; saved as typed."}
    try:
        answer = llm.complete([{"role": "system", "content": _INSTRUCTION}, {"role": "user", "content": text}],
                              timeout=60.0)
    except Exception as exc:  # LlmError is the framework's; a plugin may only match it by name
        return {"title": FALLBACK_TITLE, "text": text, "tidied": False, "note": f"Compass could not answer: {exc}"}

    lines = _unwrap(answer).split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    match = _TITLE_LINE.match(lines[first]) if first is not None else None
    if match is None:
        return {"title": FALLBACK_TITLE, "text": text, "tidied": False, "note": "Compass answered in the wrong shape."}
    title = _title_from(match.group(1)) or FALLBACK_TITLE
    body = "\n".join(lines[first + 1:]).strip("\n")
    if _structure_kept(text, body):
        return {"title": title, "text": body, "tidied": True, "note": ""}
    # The title is still good; only the text is distrusted.
    return {"title": title, "text": text, "tidied": False,
            "note": "Compass changed more than the typing, so the text was kept as you typed it."}
