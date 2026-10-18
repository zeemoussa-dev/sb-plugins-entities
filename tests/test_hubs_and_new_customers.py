"""Partner hubs alongside Customer hubs (a Cost Manager customer may link to
either), and a top-level Customer made at once rather than through discovery."""
import pytest

from backend.customers import Customers
from backend.opportunities import Opportunities, OpportunityError, OpportunityNotFound
from backend.registry import EntitiesRegistry
from test_opportunities import FakeApi, service, vault, write  # noqa: F401 -- fixtures

COMMITMENT = {"type": "MACC", "amount": 5000000, "currency": "USD", "start": "2026-01-01", "end": "2028-12-31"}


@pytest.fixture()
def partners(vault):  # noqa: F811
    root = vault / "Work" / "Partners" / "Northwind"
    write(root / "Affiliates" / "North Health" / "North Health.md",
          '---\ntype: "Partner"\nname: "North Health"\ntags: ["partner/north-health"]\n---\n')
    write(root / "Affiliates" / "North Health" / "Affiliates" / "Clinic" / "Clinic.md",
          '---\ntype: "Partner"\nname: "Clinic"\ntags: ["partner/clinic"]\n---\n')
    return vault


@pytest.fixture()
def api(partners):
    return FakeApi(partners)


def test_hubs_lists_both_kinds_with_partner_affiliates_nested(api):
    hubs = Opportunities(api).hubs()
    assert [(h["kind"], h["stem"]) for h in hubs] == [
        ("customer", "Contoso"), ("customer", "Fabrikam"), ("partner", "Northwind")]
    northwind = hubs[-1]
    assert northwind["tag"] == "partner/northwind"
    assert northwind["affiliates"][0]["stem"] == "North Health"
    assert northwind["affiliates"][0]["affiliates"] == [
        {"kind": "partner", "name": "Clinic", "stem": "Clinic", "tag": "partner/clinic", "affiliates": []}]
    assert hubs[0]["affiliates"][0]["stem"] == "Contoso Labs"


def test_customers_still_lists_customers_only(api):
    assert [c["stem"] for c in Opportunities(api).customers()] == ["Contoso", "Fabrikam"]


def test_a_commitment_can_sit_on_a_partner_and_its_deep_affiliate(api, partners):
    customers = Customers(api)
    assert customers.set_commitment("Clinic", COMMITMENT)["amount"] == 5000000
    text = (partners / "Work/Partners/Northwind/Affiliates/North Health/Affiliates/Clinic/Clinic.md").read_text("utf-8")
    assert "macc_amount: 5000000" in text
    assert customers.commitment("Northwind") is None


def test_a_partner_pipeline_is_its_own_and_its_affiliates(api, partners):
    service = Opportunities(api)
    service.create("Clinic", "Clinic Cloud", {}, [])
    assert [o["title"] for o in service.list_for_customer("Northwind")] == ["Clinic Cloud"]
    assert [o["title"] for o in service.list_for_customer("North Health")] == ["Clinic Cloud"]
    assert service.list_for_customer("North Health", include_affiliates=False) == []


def test_a_stem_under_both_kinds_is_ambiguous(api, partners):
    write(partners / "Work" / "Partners" / "Contoso" / "Contoso.md",
          '---\ntype: "Partner"\nname: "Contoso"\ntags: ["partner/contoso"]\n---\n')
    with pytest.raises(OpportunityError, match="more than one hub"):
        Customers(api).commitment("Contoso")


def test_no_customer_affiliate_under_a_partner(api):
    with pytest.raises(OpportunityError, match="Partner"):
        Opportunities(api).create_affiliate("Northwind", "Northwind East")


def test_create_customer_makes_a_top_level_hub_with_its_children_and_registry_row(api, partners):
    made = Opportunities(api).create_customer("Q Mobility", aliases=["Q MOBILITY - L.L.C."])
    assert made == {"name": "Q Mobility", "stem": "Q Mobility", "tag": "customer/q-mobility"}

    folder = partners / "Work" / "Customers" / "Q Mobility"
    hub = (folder / "Q Mobility.md").read_text("utf-8")
    assert 'type: "Customer"' in hub and 'affiliate_of: ""' in hub
    assert 'aliases: ["Q MOBILITY - L.L.C."]' in hub
    assert 'tags: ["kind/customer", "customer/q-mobility"]' in hub
    assert "## Personal Notes" in hub and "[[Q Mobility-captures|Captures]]" in hub
    assert "customer/q-mobility" in (folder / "Q Mobility-captures.md").read_text("utf-8")

    row = EntitiesRegistry(api).find_entity("Q Mobility")
    assert row["section"] == "customer" and row["created"] and row["affiliate_of"] == ""
    assert "Q Mobility" in [c["stem"] for c in Opportunities(api).customers()]
    assert Customers(api).commitment("Q Mobility") is None


def test_create_customer_refuses_a_name_already_taken(api):
    service = Opportunities(api)
    with pytest.raises(OpportunityError, match="already"):
        service.create_customer("Contoso")
    with pytest.raises(OpportunityError, match="already"):
        service.create_customer("Northwind")
    service.create_customer("Astra Tech")
    with pytest.raises(OpportunityError, match="already"):
        service.create_customer("Astra Tech")


def test_an_unknown_stem_is_still_not_found(api):
    with pytest.raises(OpportunityNotFound):
        Customers(api).commitment("Nobody")


def test_bulk_commitments_answer_every_hub_from_one_walk(api):
    customers = Customers(api)
    customers.set_commitment("Contoso", COMMITMENT)
    every = customers.commitments()
    assert every["Contoso"]["amount"] == 5000000
    assert every["Fabrikam"] is None and every["Clinic"] is None
    assert customers.commitments(["Contoso", "Nobody"]) == {"Contoso": every["Contoso"]}


def test_bulk_insights(api):
    customers = Customers(api)
    customers.set_insight("Fabrikam", {"terms": [{"model": "yearly", "start": "2026-01-01", "amount": 5}]})
    found = customers.insights(["Contoso", "Fabrikam"])
    assert found["Contoso"] is None and found["Fabrikam"]["terms"][0]["amount"] == 5


def test_a_hub_edited_outside_this_plugin_is_read_fresh(api, partners, monkeypatch):
    from backend import opportunities as opp

    customers = Customers(api)
    assert customers.commitment("Fabrikam") is None
    hub = partners / "Work" / "Customers" / "Fabrikam" / "Fabrikam.md"
    text = hub.read_text("utf-8").replace('name: "Fabrikam"\n', 'name: "Fabrikam"\nmacc_type: "MACC"\nmacc_amount: 7\n')
    hub.write_text(text, encoding="utf-8")
    # The hub list is remembered briefly; once it lapses the changed file is re-read.
    monkeypatch.setattr(opp, "HUB_LIST_SECONDS", 0)
    assert customers.commitment("Fabrikam")["amount"] == 7


def test_a_hub_made_by_this_plugin_lists_at_once_despite_the_remembered_list(api):
    service = Opportunities(api)
    assert "Astra Tech" not in [c["stem"] for c in service.customers()]
    service.create_customer("Astra Tech")
    assert "Astra Tech" in [c["stem"] for c in service.customers()]
