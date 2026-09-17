"""Cockpit agent matching by Customer (the framework's `BUG-063`, now owned here).

Ported from the framework's `moderator.match_customer_expert` /
`match_customer_fallback_agent` with the same rules:
- a subject's customer is its `customer:` frontmatter, else its `customer/<slug>` tag;
- its dedicated Expert is the `<slug>-expert` agent in the Customer Section;
- only when no dedicated Expert exists does the Customer Section's fallback agent answer;
- a subject with no customer gets neither.
"""
from __future__ import annotations

import re

_TAG_INVALID_CHARS = re.compile(r"[^a-z0-9/]+")


def tag_slug(text: str) -> str:
    """The framework's own tag slug: lowercase, runs of anything else collapsed to one hyphen."""
    slug = _TAG_INVALID_CHARS.sub("-", text.lower()).strip("-")
    return slug or "untitled"


# The Customer Section's id is the slug of its name.
CUSTOMER_SECTION_ID = tag_slug("Customer")


def subject_customer(subject: dict) -> str | None:
    customer = subject["frontmatter"].get("customer")
    if customer:
        return str(customer)
    for tag in subject["tags"]:
        if tag.startswith("customer/"):
            return tag.split("/", 1)[1]
    return None


class CockpitAgentMatcher:
    def __init__(self, api) -> None:
        self._api = api

    def match(self, subject_kind: str, subject: dict) -> dict:
        customer = subject_customer(subject)
        if not customer:
            return {"experts": [], "fallback_agent_id": None}
        expert_id = f"{tag_slug(customer)}-expert"
        if any(
            expert["id"] == expert_id and expert["section_id"] == CUSTOMER_SECTION_ID
            for expert in self._api.agents.list_experts()
        ):
            return {"experts": [expert_id], "fallback_agent_id": None}
        section = self._api.sections.get(CUSTOMER_SECTION_ID)
        return {"experts": [], "fallback_agent_id": section["fallback_agent_id"] if section else None}
