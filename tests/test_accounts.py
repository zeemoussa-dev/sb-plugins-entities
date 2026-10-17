"""The Customers & Partners screens' backend against a real folder of notes."""
from pathlib import Path

import pytest

from backend.accounts import AccountConflict, Accounts
from backend.opportunities import OpportunityError, OpportunityNotFound, _today
from test_opportunities import FakeApi, hub, write

CAPTURES = ('---\ntype: "Captures"\nname: "Contoso Captures"\nparent: "[[Contoso]]"\n'
            'tags: ["customer/contoso", "kind/captures"]\n---\n\n# Contoso\n\nIntro.\n\n'
            "## Notes\n\n- 2026-10-01: met the CIO\n\n## Captured\n\n- automated line\n")


class CostService:
    def __init__(self):
        self.asked = []

    def for_entity(self, stem):
        self.asked.append(stem)
        return {"id": "contoso", "signed": 1000, "route": "/azure-cost-manager/report?customer=contoso"} \
            if stem == "Contoso" else None


@pytest.fixture()
def vault(tmp_path):
    customers = tmp_path / "Work" / "Customers"
    hub(customers / "Contoso" / "Contoso.md", "Contoso", "customer/contoso",
        extra='domain: "contoso.com"\nmacc_type: "MACC"\nmacc_amount: 1000\nmacc_start: "2026-01-01"\n'
              'macc_end: "2027-01-01"\n',
        body="\nIntro text.\n\n## Summary\n\nBig account.\n\n## Personal Notes\n\nMy own words.\n\n"
             "## Actions\n\n## Opportunities\n\n")
    hub(customers / "Contoso" / "Affiliates" / "Contoso Labs" / "Contoso Labs.md", "Contoso Labs",
        "customer/contoso-labs", body="\n## Summary\n\n## Actions\n\n")
    write(customers / "Contoso" / "Contoso-captures.md", CAPTURES)
    write(customers / "Contoso" / "People" / "ann@contoso.com.md",
          '---\ntype: "Person"\nname: "Ann"\nemail: "ann@contoso.com"\ntags: ["kind/person"]\n---\n')
    write(tmp_path / "Work" / "People" / "bob.md",
          '---\ntype: "Person"\nname: "Bob"\ntags: ["kind/person", "customer/contoso"]\n---\n')
    write(customers / "Contoso" / "Opportunities" / "Deal" / "Deal.md",
          '---\ntype: "Opportunity"\nid: "d1"\ntitle: "Deal"\nstatus: "Open"\nstage: "Identified"\n'
          'product: ["azure"]\nroute: "csp"\npartner: ["Northwind"]\ntags: ["kind/opportunity"]\n---\n')
    partners = tmp_path / "Work" / "Partners"
    write(partners / "Northwind" / "Northwind.md",
          '---\ntype: "Partner"\nname: "Northwind"\ntags: ["partner/northwind"]\n---\n\n## Summary\n\n')
    write(partners / "Northwind" / "Affiliates" / "North Labs" / "North Labs.md",
          '---\ntype: "Partner"\nname: "North Labs"\ntags: ["partner/north-labs"]\n---\n')
    write(partners / "Northwind" / "Affiliates" / "North Labs" / "Affiliates" / "Tiny" / "Tiny.md",
          '---\ntype: "Partner"\nname: "Tiny"\ntags: ["partner/tiny"]\n---\n')
    write(tmp_path / "Work" / "Meetings" / "Kickoff" / "Kickoff.md",
          '---\ntype: "Meeting"\ntitle: "Kickoff"\nstart: "2026-10-02 09:00:00+00:00"\n'
          'tags: ["kind/meeting", "customer/contoso"]\n---\n')
    return tmp_path


def thread(vault: Path, name: str, tags: str, last: str):
    write(vault / "Work" / "Threads" / name / f"{name}.md",
          f'---\ntype: "Thread"\ntags: {tags}\nthread_name: "{name} subject"\nlast_message_at: "{last}"\n---\n\nbody\n')


@pytest.fixture()
def api(vault):
    # Threads are written before the snapshot but the index never sees them in a
    # real install; the service must find them on disk either way.
    thread(vault, "T1", '["customer/contoso"]', "2026-10-05 10:00:00+00:00")
    thread(vault, "T2", '["customer/fabrikam"]', "2026-10-06 10:00:00+00:00")
    fake = FakeApi(vault)
    fake.cost = CostService()
    fake.get_service = lambda name: fake.cost if name == "azure-cost-manager.portfolio" else None
    return fake


@pytest.fixture()
def accounts(api):
    return Accounts(api)


def hub_text(vault, *parts):
    return vault.joinpath("Work", *parts).read_text(encoding="utf-8")


# -- the list ------------------------------------------------------------------


def test_the_list_holds_every_hub_with_affiliates_under_their_parent(accounts):
    listed = accounts.list()
    customers = {row["stem"]: row for row in listed["customers"]}
    partners = {row["stem"]: row for row in listed["partners"]}

    assert set(customers) == {"Contoso", "Contoso Labs"}
    assert customers["Contoso Labs"]["parent"] == "Contoso"
    assert customers["Contoso"]["affiliates"] == 1
    assert customers["Contoso"]["opportunities"] == 1
    assert customers["Contoso"]["people"] == 2
    assert customers["Contoso"]["has_commitment"] is True
    assert customers["Contoso"]["domain"] == "contoso.com"
    # A Partner's affiliates nest more than one level deep.
    assert partners["Tiny"]["parent"] == "North Labs"
    assert partners["North Labs"]["parent"] == "Northwind"


# -- one hub -------------------------------------------------------------------


def test_a_customer_page_gathers_its_data(accounts, api):
    page = accounts.detail("customer", "Contoso")

    assert page["intro"] == "Intro text."
    assert [s["name"] for s in page["sections"]] == ["Summary", "Personal Notes", "Actions", "Opportunities"]
    assert page["personal_notes"] == "My own words."
    assert page["captures"] == {"exists": True, "notes": "- 2026-10-01: met the CIO", "captured": "- automated line"}
    assert [p["name"] for p in page["people"]] == ["Ann", "Bob"]
    assert [o["title"] for o in page["opportunities"]] == ["Deal"]
    assert page["affiliates"] == [{"name": "Contoso Labs", "stem": "Contoso Labs"}]
    assert page["commitment"]["amount"] == 1000
    assert "cost" not in page
    assert accounts.cost("customer", "Contoso") == {"available": True, "row": {"id": "contoso", "signed": 1000,
                                                       "route": "/azure-cost-manager/report?customer=contoso"}}


def test_activity_is_meetings_and_threads_with_the_tag_newest_first(accounts):
    activity = accounts.detail("customer", "Contoso")["activity"]
    assert [(a["kind"], a["stem"]) for a in activity] == [("thread", "T1"), ("meeting", "Kickoff")]
    assert activity[0]["title"] == "T1 subject"


def test_a_partner_page_lists_the_opportunities_naming_it_and_its_lineage(accounts, api):
    assert [o["title"] for o in accounts.detail("partner", "Northwind")["opportunities"]] == ["Deal"]
    tiny = accounts.detail("partner", "Tiny")
    assert [h["stem"] for h in tiny["lineage"]] == ["Northwind", "North Labs"]
    assert accounts.cost("partner", "Tiny") == {"available": False, "row": None}
    assert api.cost.asked == []


def test_no_cost_service_means_no_cost_panel(vault):
    fake = FakeApi(vault)
    fake.get_service = lambda name: None
    assert Accounts(fake).cost("customer", "Contoso") == {"available": False, "row": None}


def test_a_failing_cost_service_does_not_fail_the_page(accounts, api):
    def broken(stem):
        raise RuntimeError("sync in progress")
    api.cost.for_entity = broken
    assert accounts.cost("customer", "Contoso")["error"] == "sync in progress"


def test_an_unknown_hub_or_kind_is_not_found(accounts):
    with pytest.raises(OpportunityNotFound):
        accounts.detail("customer", "Nobody")
    with pytest.raises(OpportunityNotFound):
        accounts.detail("people", "Contoso")
    with pytest.raises(OpportunityNotFound):
        accounts.detail("partner", "Contoso")


# -- writing -------------------------------------------------------------------


def test_personal_notes_are_replaced_and_nothing_else_changes(accounts, vault):
    before = hub_text(vault, "Customers", "Contoso", "Contoso.md")
    assert accounts.set_personal_notes("customer", "Contoso", "New words.\r\n\r\n- a point  ", "My own words.") \
        == "New words.\n\n- a point"
    after = hub_text(vault, "Customers", "Contoso", "Contoso.md")
    assert after == before.replace("My own words.", "New words.\n\n- a point")


def test_personal_notes_changed_meanwhile_are_not_overwritten(accounts, vault):
    with pytest.raises(AccountConflict):
        accounts.set_personal_notes("customer", "Contoso", "Mine", "what the page saw long ago")
    assert "My own words." in hub_text(vault, "Customers", "Contoso", "Contoso.md")


def test_a_hub_without_personal_notes_gets_the_section_before_actions(accounts, vault):
    accounts.set_personal_notes("customer", "Contoso Labs", "Hello", "")
    text = hub_text(vault, "Customers", "Contoso", "Affiliates", "Contoso Labs", "Contoso Labs.md")
    assert text.index("## Personal Notes\n\nHello") < text.index("## Actions")


def test_a_capture_is_appended_under_notes_dated_today(accounts, vault):
    captures = accounts.add_capture("customer", "Contoso", "Heard in the lift\nsecond line")
    assert captures["notes"] == f"- 2026-10-01: met the CIO\n\n- {_today()}: Heard in the lift\n  second line"
    assert captures["captured"] == "- automated line"
    text = hub_text(vault, "Customers", "Contoso", "Contoso-captures.md")
    assert text.startswith(CAPTURES.split("## Notes")[0])


def test_an_empty_capture_is_refused(accounts):
    with pytest.raises(OpportunityError):
        accounts.add_capture("customer", "Contoso", "  \n ")


def test_capture_notes_are_editable_and_captured_is_kept(accounts, vault):
    captures = accounts.set_capture_notes("customer", "Contoso", "rewritten", "- 2026-10-01: met the CIO")
    assert captures == {"exists": True, "notes": "rewritten", "captured": "- automated line"}
    with pytest.raises(AccountConflict):
        accounts.set_capture_notes("customer", "Contoso", "again", "- 2026-10-01: met the CIO")


def test_the_http_surface(api, vault):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.registry import EntitiesRegistry
    from backend.routes import build_router

    app = FastAPI()
    app.include_router(build_router(EntitiesRegistry(api), Accounts(api)), prefix="/plugins/entities")
    client = TestClient(app)
    base = "/plugins/entities/accounts"

    assert {row["stem"] for row in client.get(base).json()["customers"]} == {"Contoso", "Contoso Labs"}
    assert client.get(f"{base}/customer/Contoso%20Labs").json()["lineage"] == [{"name": "Contoso", "stem": "Contoso"}]
    assert client.get(f"{base}/customer/Nobody").status_code == 404
    assert client.get(f"{base}/customer/Contoso/cost").json()["row"]["id"] == "contoso"
    stale = client.put(f"{base}/customer/Contoso/personal-notes", json={"text": "x", "previous": "old"})
    assert stale.status_code == 409
    assert client.put(f"{base}/customer/Contoso/personal-notes",
                      json={"text": "x", "previous": "My own words."}).json() == {"text": "x"}
    assert client.post(f"{base}/customer/Contoso/captures", json={"text": " "}).status_code == 400
    assert client.post(f"{base}/customer/Contoso/captures", json={"text": "hi"}).json()["notes"].endswith(": hi")


def test_a_hub_with_no_captures_note_gets_one_on_its_first_capture(accounts, vault):
    captures = accounts.add_capture("partner", "Northwind", "First")
    assert captures["notes"] == f"- {_today()}: First"
    text = hub_text(vault, "Partners", "Northwind", "Northwind-captures.md")
    assert 'tags: ["partner/northwind", "kind/captures"]' in text
    assert text.index("## Notes") < text.index("## Captured")
