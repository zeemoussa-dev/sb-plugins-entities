"""The `entities.opportunities` service against a real folder of notes and a
stand-in for the Plugin API's reads.

The stand-in's index is taken once, when the vault is laid out, the way the
framework's index is rebuilt on its own schedule: an opportunity created during a
test is not in it, so these tests also prove the service never waits for a reindex.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest

from backend import opportunities as opp
from backend.opportunities import Opportunities, OpportunityError, OpportunityNotFound

TODAY = date.today().isoformat()
TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "opportunity" / "Template.json"

_LINE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s?(.*)$")


def _parse(raw):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if raw.startswith("[") and raw.endswith("]"):
        return re.findall(r'"((?:[^"\\]|\\.)*)"', raw[1:-1])
    return raw


def read_note(path):
    text = Path(opp._long(path)).read_text(encoding="utf-8")
    if not text.startswith("---\n") or text.find("\n---\n", 4) == -1:
        return {}, text
    end = text.find("\n---\n", 4)
    frontmatter = {}
    for line in text[4:end].splitlines():
        match = _LINE.match(line)
        if match:
            frontmatter[match.group(1)] = _parse(match.group(2))
    return frontmatter, text[end + 5:]


def read_section(path, header):
    text = Path(opp._long(path)).read_text(encoding="utf-8")
    heading = header if header.startswith("#") else f"## {header}"
    match = re.search(r"^" + re.escape(heading) + r"$", text, re.M)
    if match is None:
        return None
    following = re.search(r"^## .+$", text[match.end():], re.M)
    section = text[match.end():match.end() + following.start()] if following else text[match.end():]
    return section.strip() or None


class FakeApi:
    def __init__(self, vault: Path):
        work = vault / "Work"
        snapshot = []
        for path in sorted(work.rglob("*.md")):
            frontmatter, _ = read_note(path)
            tags = frontmatter.get("tags") if isinstance(frontmatter.get("tags"), list) else []
            snapshot.append({"path": str(path), "stem": path.stem, "frontmatter": frontmatter, "tags": tags})
        self.vault = type("Vault", (), {
            "entries": staticmethod(lambda: list(snapshot)),
            "read_note": staticmethod(read_note),
            "read_section": staticmethod(read_section),
        })()
        self.data = FakeData()


class FakeData:
    def __init__(self):
        self.files = {}

    def read_text(self, path):
        return self.files.get(path)

    def write_text(self, path, content):
        self.files[path] = content


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def hub(path: Path, name: str, tag: str, extra: str = "", body: str = "\n## Summary\n\n## Opportunities\n\n"):
    write(path, f'---\ntype: "Customer"\nname: "{name}"\n{extra}tags: ["kind/customer", "{tag}"]\n---\n{body}')


V2_NOTE = (
    '---\ntype: "Opportunity"\nid: "v2-id"\ntitle: "Legacy Deal"\ncustomer: "Contoso"\nstatus: "Open"\n'
    'stage: "Qualified"\nproduct: ["azure"]\nroute: "direct-ea-mca"\ndraws_against: ""\npartner: []\n'
    'technologies: []\nexpected_consumption: ""\nexpected_monthly_usd: 4000\ncreated: "2026-01-02"\n'
    'updated: "2026-01-02"\ntags: ["kind/opportunity", "customer/contoso"]\n---\n\n'
    "## Summary\n\nA deal from before Template v3.\n\n## Actions\n\n- Call them\n\n## Related\n\n- [[Contoso]]\n\n"
    "## History & Captures\n\n- [[Legacy Deal-history|History]]\n- [[Legacy Deal-captures|Captures]]\n"
)


@pytest.fixture()
def vault(tmp_path):
    customers = tmp_path / "Work" / "Customers"
    hub(customers / "Contoso" / "Contoso.md", "Contoso", "customer/contoso")
    hub(customers / "Contoso" / "Affiliates" / "Contoso Labs" / "Contoso Labs.md", "Contoso Labs",
        "customer/contoso-labs", extra='affiliate_of: "[[Contoso]]"\n', body="\n## Summary\n\nNo opportunities yet.\n")
    hub(customers / "Fabrikam" / "Fabrikam.md", "Fabrikam", "customer/fabrikam")
    write(tmp_path / "Work" / "Partners" / "Northwind" / "Northwind.md",
          '---\ntype: "Partner"\nname: "Northwind"\ntags: ["partner/northwind"]\n---\n')
    legacy = customers / "Contoso" / "Opportunities" / "Legacy Deal"
    write(legacy / "Legacy Deal.md", V2_NOTE)
    write(legacy / "Legacy Deal-history.md",
          '---\ntype: "History"\nname: "Legacy Deal History"\nparent: "[[Legacy Deal]]"\n---\n\n# Legacy Deal\n\n'
          "## Log\n\n- 2026-01-02: opened\n")
    # Not an opportunity: a folder whose note is not named after it.
    write(customers / "Contoso" / "Opportunities" / "Notes" / "scratch.md", "loose text\n")
    return tmp_path


@pytest.fixture()
def service(vault):
    return Opportunities(FakeApi(vault))


def opportunity_folder(vault, *parts):
    return vault.joinpath("Work", "Customers", *parts)


# -- the Template ----------------------------------------------------------------


def test_the_service_writes_what_template_v3_describes():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    root = template["root"]

    assert template["version"] == opp.TEMPLATE_VERSION == 3
    assert root["frontmatter_key_order"] == opp.KEY_ORDER
    assert root["frontmatter_defaults"] == opp.DEFAULTS
    assert {k: v for k, v in root["frontmatter_enums"].items()} == opp.ENUMS
    assert [s["name"] for s in root["sections"]] == opp.SECTIONS
    assert [(c["suffix"], c["frontmatter_defaults"]["type"], c["frontmatter_defaults"]["tags"], c["display_label"])
            for c in root["children"]] == [(c["suffix"], c["type"], [c["tag"]], c["label"]) for c in opp.CHILDREN]
    assert template["parent"]["link_back_section"] == f"## {opp.LINK_BACK_SECTION}"
    assert root["children_index_section"] == "History & Captures"


# -- customers and listing --------------------------------------------------------


def test_customers_lists_every_hub_with_its_affiliates(service):
    assert service.customers() == [
        {"name": "Contoso", "stem": "Contoso", "tag": "customer/contoso",
         "affiliates": [{"name": "Contoso Labs", "stem": "Contoso Labs", "tag": "customer/contoso-labs"}]},
        {"name": "Fabrikam", "stem": "Fabrikam", "tag": "customer/fabrikam", "affiliates": []},
    ]


def test_a_template_v2_note_lists_with_empty_v3_fields(service):
    [legacy] = service.list_for_customer("Contoso")

    assert legacy == {
        "id": "v2-id", "title": "Legacy Deal", "stem": "Legacy Deal", "customer": "Contoso", "affiliate": None,
        "status": "Open", "stage": "Qualified", "product": ["azure"], "route": "direct-ea-mca", "partner": [],
        "billing_profile": "", "consumption_start": "", "expected_monthly_usd": 4000, "plan": [],
        "updated": "2026-01-02", "created": "2026-01-02", "technologies": [],
    }


def test_listing_covers_the_affiliates_opportunities_unless_told_not_to(service):
    service.create("Contoso Labs", "Labs GPU", {}, [{"month": "2026-12", "usd": 900}])

    every = service.list_for_customer("Contoso")
    own = service.list_for_customer("Contoso", include_affiliates=False)

    assert [(o["title"], o["affiliate"]) for o in every] == [("Legacy Deal", None), ("Labs GPU", "Contoso Labs")]
    assert [o["title"] for o in own] == ["Legacy Deal"]
    assert every[1]["customer"] == "Contoso"


def test_an_unknown_customer_is_refused(service):
    with pytest.raises(OpportunityNotFound):
        service.list_for_customer("Nobody")
    with pytest.raises(ValueError):
        service.list_for_customer("../Contoso")


# -- create ----------------------------------------------------------------------


def test_create_writes_the_note_its_children_and_the_link_back(service, vault):
    created = service.create("Contoso", "Data Platform", {
        "stage": "Proposed", "product": ["azure"], "route": "direct-ea-mca", "partner": ["northwind"],
        "billing_profile": "12345678",
    }, [{"month": "2027-02", "usd": 3000}, {"month": "2027-01", "usd": "1500"}])

    folder = opportunity_folder(vault, "Contoso", "Opportunities", "Data Platform")
    text = (folder / "Data Platform.md").read_text(encoding="utf-8")
    frontmatter, _ = read_note(folder / "Data Platform.md")

    assert list(frontmatter) == opp.KEY_ORDER
    # Byte for byte what the vault engine's own `create` writes for this Template.
    assert text == (
        '---\ntype: "Opportunity"\nid: "' + created["id"] + '"\ntitle: "Data Platform"\ncustomer: "Contoso"\n'
        'status: "Open"\nstage: "Proposed"\nproduct: ["azure"]\nroute: "direct-ea-mca"\ndraws_against: ""\n'
        'partner: ["Northwind"]\ntechnologies: []\nbilling_profile: "12345678"\nconsumption_start: "2027-01"\n'
        f'expected_consumption: ""\nexpected_monthly_usd: 3000\ncreated: "{TODAY}"\nupdated: "{TODAY}"\n'
        'tags: ["kind/opportunity", "customer/contoso"]\n---\n'
        "\n## Summary\n\n\n\n## Consumption Plan\n\n| Month | USD |\n|---|---|\n| 2027-01 | 1500 |\n"
        "| 2027-02 | 3000 |\n\n## Actions\n\n\n\n## Related\n\n- [[Contoso]]\n- [[Northwind]]\n\n"
        "## History & Captures\n\n- [[Data Platform-history|History]]\n- [[Data Platform-captures|Captures]]\n"
    )
    assert (folder / "Data Platform-history.md").read_text(encoding="utf-8") == (
        '---\ntype: "History"\ntags: ["kind/history"]\nname: "Data Platform History"\n'
        'parent: "[[Data Platform]]"\n---\n\n# Data Platform\n\n')
    assert (folder / "Data Platform-captures.md").exists()
    hub_text = opportunity_folder(vault, "Contoso", "Contoso.md").read_text(encoding="utf-8")
    assert "## Opportunities\n\n- [[Data Platform]]\n" in hub_text
    assert created["plan"] == [{"month": "2027-01", "usd": 1500}, {"month": "2027-02", "usd": 3000}]
    assert created["expected_monthly_usd"] == 3000 and created["partner"] == ["Northwind"]


def test_an_affiliate_opportunity_lives_under_the_affiliate_and_carries_its_tag(service, vault):
    service.create("Contoso Labs", "Labs GPU", {}, [])

    folder = opportunity_folder(vault, "Contoso", "Affiliates", "Contoso Labs", "Opportunities", "Labs GPU")
    frontmatter, body = read_note(folder / "Labs GPU.md")
    hub_text = opportunity_folder(vault, "Contoso", "Affiliates", "Contoso Labs", "Contoso Labs.md").read_text(
        encoding="utf-8")

    assert frontmatter["customer"] == "Contoso Labs"
    assert frontmatter["tags"] == ["kind/opportunity", "customer/contoso-labs"]
    assert frontmatter["expected_monthly_usd"] == ""
    assert "## Consumption Plan\n\n| Month | USD |\n|---|---|\n" in body
    # The affiliate hub had no `## Opportunities`; it gains one.
    assert hub_text.endswith("## Opportunities\n\n- [[Labs GPU]]\n")


def test_create_can_write_the_summary_and_actions_only(service, vault):
    service.create("Contoso", "AI Grounding", {}, [], {"Summary": "Why them.\n\n- runs Fabric", "Actions": "- Workshop"})

    _, body = read_note(opportunity_folder(vault, "Contoso", "Opportunities", "AI Grounding", "AI Grounding.md"))

    assert "## Summary\n\nWhy them.\n\n- runs Fabric\n" in body and "## Actions\n\n- Workshop\n" in body
    with pytest.raises(ValueError, match="only Summary, Actions"):
        service.create("Contoso", "Other", {}, [], {"Related": "- [[X]]"})


def test_create_refuses_what_the_template_forbids(service):
    cases = [
        ("Legacy Deal", {}, []),                                  # title taken
        ("legacy deal", {}, []),                                  # taken, as Windows sees a file name
        ("A/B", {}, []),                                          # not a file name
        ("..", {}, []),
        ("Deal", {"status": "Maybe"}, []),
        ("Deal", {"product": ["mainframe"]}, []),
        ("Deal", {"partner": ["Nobody"]}, []),
        ("Deal", {"status": "Won"}, []),                          # Won needs Closed
        ("Deal", {"stage": "Closed"}, []),                        # Closed needs Won/Lost
        ("Deal", {"route": "csp", "draws_against": "MACC"}, []),
        ("Deal", {"draws_against": "MACC"}, []),                  # route unknown cannot draw
        ("Deal", {"expected_monthly_usd": "lots"}, []),
        ("Deal", {"expected_monthly_usd": 10}, [{"month": "2027-01", "usd": 20}]),
        ("Deal", {"consumption_start": "2027-03"}, [{"month": "2027-01", "usd": 20}]),
        ("Deal", {"consumption_start": "March"}, []),
        ("Deal", {"title": "Other"}, []),                         # not a settable field
        ("Deal", {}, [{"month": "2027-1", "usd": 1}]),
        ("Deal", {}, [{"month": "2027-01", "usd": -1}]),
        ("Deal", {}, [{"month": "2027-01", "usd": 1}, {"month": "2027-01", "usd": 2}]),
    ]
    for title, fields, plan in cases:
        with pytest.raises(ValueError):
            service.create("Contoso", title, fields, plan)
    with pytest.raises(OpportunityNotFound):
        service.create("Nobody", "Deal", {}, [])


def test_a_closed_win_is_accepted(service):
    created = service.create("Fabrikam", "Won Deal", {"status": "Won", "stage": "Closed"}, [])

    assert (created["status"], created["stage"]) == ("Won", "Closed")


# -- update ----------------------------------------------------------------------


def test_update_rewrites_the_plan_and_logs_the_change(service, vault):
    created = service.create("Contoso", "Data Platform", {}, [{"month": "2027-01", "usd": 1000}])

    updated = service.update(created["id"], {"stage": "Committed"},
                             [{"month": "2027-01", "usd": 1000}, {"month": "2027-02", "usd": 2500}])

    folder = opportunity_folder(vault, "Contoso", "Opportunities", "Data Platform")
    body = (folder / "Data Platform.md").read_text(encoding="utf-8")
    history = (folder / "Data Platform-history.md").read_text(encoding="utf-8")
    assert updated["stage"] == "Committed" and updated["expected_monthly_usd"] == 2500
    assert updated["plan"][-1] == {"month": "2027-02", "usd": 2500}
    assert "| 2027-01 | 1000 |\n| 2027-02 | 2500 |\n\n## Actions" in body
    assert body.count("## Consumption Plan") == 1
    assert history.endswith(
        f"## Log\n\n- {TODAY}: updated stage Identified -> Committed; expected_monthly_usd 1000 -> 2500; "
        "Consumption Plan 2027-01 to 2027-02, 2500 USD a month at the end (entities.opportunities)\n")


def test_updating_a_v2_note_brings_it_to_v3_and_keeps_every_other_line(service, vault):
    service.update("v2-id", {"billing_profile": "87654321"})

    folder = opportunity_folder(vault, "Contoso", "Opportunities", "Legacy Deal")
    text = (folder / "Legacy Deal.md").read_text(encoding="utf-8")
    expected = V2_NOTE.replace(
        'technologies: []\n', 'technologies: []\nbilling_profile: "87654321"\nconsumption_start: ""\n'
    ).replace('updated: "2026-01-02"', f'updated: "{TODAY}"').replace(
        "## Actions", "## Consumption Plan\n\n| Month | USD |\n|---|---|\n\n## Actions")
    assert text == expected
    history = (folder / "Legacy Deal-history.md").read_text(encoding="utf-8")
    assert history.endswith(f"- 2026-01-02: opened\n\n- {TODAY}: updated billing_profile \"\" -> 87654321 "
                            "(entities.opportunities)\n")


def test_an_unchanged_update_writes_nothing(service, vault):
    note = opportunity_folder(vault, "Contoso", "Opportunities", "Legacy Deal", "Legacy Deal.md")

    result = service.update("v2-id", {"stage": "Qualified"})

    assert note.read_text(encoding="utf-8") == V2_NOTE
    assert result["stage"] == "Qualified"


def test_update_refuses_what_the_template_forbids(service):
    created = service.create("Contoso", "Data Platform", {}, [{"month": "2027-01", "usd": 1000}])

    with pytest.raises(ValueError):
        service.update(created["id"], {"expected_monthly_usd": 5})   # the plan says 1000
    with pytest.raises(ValueError):
        service.update(created["id"], {"status": "Lost"})            # stage is not Closed
    with pytest.raises(ValueError):
        service.update(created["id"], {"customer": "Fabrikam"})
    with pytest.raises(OpportunityNotFound):
        service.update("no-such-id", {})
    assert service.update(created["id"], {"status": "Lost", "stage": "Closed"})["status"] == "Lost"


def test_an_empty_plan_clears_the_table_but_keeps_the_steady_state(service):
    created = service.create("Contoso", "Data Platform", {}, [{"month": "2027-01", "usd": 1000}])

    cleared = service.update(created["id"], {}, [])

    assert cleared["plan"] == [] and cleared["expected_monthly_usd"] == 1000


def test_a_path_past_the_windows_limit_is_written_and_read(service, vault):
    title = "A very long opportunity title " + "x" * 120

    created = service.create("Contoso Labs", title, {}, [{"month": "2027-01", "usd": 1}])
    updated = service.update(created["id"], {"stage": "Qualified"})

    assert updated["stage"] == "Qualified"
    assert [o["title"] for o in service.list_for_customer("Contoso Labs")] == [title]


# -- create_affiliate --------------------------------------------------------------

CUSTOMER_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "customer" / "Template.json"


def test_create_affiliate_follows_the_customer_template():
    template = json.loads(CUSTOMER_TEMPLATE.read_text(encoding="utf-8"))
    root = template["root"]

    assert root["frontmatter_defaults"] == opp.CUSTOMER_DEFAULTS
    assert [s["name"] for s in root["sections"]] == opp.CUSTOMER_SECTIONS
    assert template["parent"]["link_back_section"] == f"## {opp.AFFILIATES_SECTION}"
    assert template["parent"]["child_subpath"] == "Affiliates"
    assert [(c["suffix"], c["frontmatter_defaults"]["type"], c["frontmatter_defaults"]["tags"], c["display_label"])
            for c in root["children"]] == [(c["suffix"], c["type"], [c["tag"]], c["label"]) for c in opp.CHILDREN]


def test_create_affiliate_writes_the_hub_its_children_the_link_back_and_the_registry_row(service, vault):
    created = service.create_affiliate("Contoso", "Contoso Retail", aliases=["CR"])

    folder = opportunity_folder(vault, "Contoso", "Affiliates", "Contoso Retail")
    hub_text = (folder / "Contoso Retail.md").read_text(encoding="utf-8")
    frontmatter, _ = read_note(folder / "Contoso Retail.md")
    assert created == {"name": "Contoso Retail", "stem": "Contoso Retail", "tag": "customer/contoso-retail"}
    assert hub_text == (
        '---\ntype: "Customer"\naffiliate_of: "Contoso"\nname: "Contoso Retail"\naliases: ["CR"]\n'
        f'id: "{frontmatter["id"]}"\ntitle: "Contoso Retail"\ncreated: "{TODAY}"\n'
        'tags: ["kind/customer", "customer/contoso-retail"]\n---\n'
        "\n## Summary\n\n\n\n## Personal Notes\n\n\n\n## Actions\n\n\n\n## Related\n\n\n\n## Affiliates\n\n\n\n"
        "## History & Captures\n\n- [[Contoso Retail-history|History]]\n- [[Contoso Retail-captures|Captures]]\n"
    )
    assert (folder / "Contoso Retail-history.md").read_text(encoding="utf-8") == (
        '---\ntype: "History"\nname: "Contoso Retail History"\nparent: "[[Contoso Retail]]"\n'
        'tags: ["kind/history", "customer/contoso-retail"]\n---\n\n# Contoso Retail\n\n')
    assert (folder / "Contoso Retail-captures.md").exists()
    parent_text = opportunity_folder(vault, "Contoso", "Contoso.md").read_text(encoding="utf-8")
    assert "\n## Affiliates\n\n- [[Contoso Retail]]\n" in parent_text
    assert "### Contoso Retail\n\n\tCompany Name: Contoso Retail\n\n\tAliases: CR\n\n\tAffiliate of: Contoso\n\n" \
           "\tCreated: Yes\n" in service._api.data.files["Settings/Entities.md"]


def test_a_new_affiliate_lists_at_once_without_a_reindex(service):
    service.create_affiliate("Contoso", "Contoso Retail")

    contoso = next(c for c in service.customers() if c["stem"] == "Contoso")
    assert [a["stem"] for a in contoso["affiliates"]] == ["Contoso Labs", "Contoso Retail"]
    assert service.list_for_customer("Contoso Retail") == []
    created = service.create("Contoso Retail", "Retail Analytics", {}, [])
    assert created["affiliate"] == "Contoso Retail" and created["customer"] == "Contoso"


def test_create_affiliate_adopts_a_company_discovery_already_registered(service, vault):
    from backend.registry import EntitiesRegistry
    EntitiesRegistry(service._api).create_entity("Contoso Retail", "customer", domain="retail.example",
                                                 aliases="cretail.example")

    service.create_affiliate("Contoso", "Contoso Retail", aliases=["CR"])

    frontmatter, _ = read_note(opportunity_folder(vault, "Contoso", "Affiliates", "Contoso Retail", "Contoso Retail.md"))
    row = EntitiesRegistry(service._api).find_entity("Contoso Retail")
    assert frontmatter["domain"] == "retail.example"
    assert frontmatter["aliases"] == ["cretail.example", "CR"]
    assert (row["affiliate_of"], row["created"], row["domain"]) == ("Contoso", True, "retail.example")
    assert row["aliases"] == "cretail.example, CR"


def test_create_affiliate_refuses_a_taken_name_or_a_bad_parent(service):
    from backend.registry import EntitiesRegistry
    registry = EntitiesRegistry(service._api)
    registry.create_entity("Gone Co", "customer")
    registry.delete_entity("Gone Co")
    registry.create_entity("Partnerish", "partner")

    for parent, name, aliases in [
        ("Contoso", "Fabrikam", None),          # a top-level Customer
        ("Contoso", "contoso labs", None),      # an affiliate, any case
        ("Contoso", "New Co", ["Fabrikam"]),    # an alias that is another hub's name
        ("Contoso", "Northwind", None),         # a Partner
        ("Contoso", "Gone Co", None),           # soft-deleted in the registry
        ("Contoso", "Partnerish", None),        # registered as a partner
        ("Contoso", "", None),
        ("Contoso", "..", None),
        ("Contoso Labs", "Labs Sub", None),     # an affiliate cannot have affiliates
    ]:
        with pytest.raises(ValueError):
            service.create_affiliate(parent, name, aliases)
    with pytest.raises(OpportunityNotFound):
        service.create_affiliate("Nobody", "New Co")
