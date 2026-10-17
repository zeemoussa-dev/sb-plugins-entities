"""Core42 Insight terms in their own note beside the hub, never on the hub."""
import pytest

from backend.customers import Customers
from backend.opportunities import OpportunityError, OpportunityNotFound
from test_opportunities import FakeApi, vault  # noqa: F401 -- fixture

TERMS = {
    "terms": [
        {"model": "percentage", "start": "2026-01-01", "end": "2026-06-30", "percent": 3.0,
         "include_marketplace": True, "subtract_credits": True},
        {"model": "yearly", "start": "2026-07-01", "amount": 20000, "billing_day": 5},
    ],
    "note": "Signed in March.",
}


@pytest.fixture()
def customers(vault):  # noqa: F811
    return Customers(FakeApi(vault))


def contoso(vault, name):  # noqa: F811
    return vault / "Work" / "Customers" / "Contoso" / name


def test_no_note_means_no_insight(customers):
    assert customers.insight("Contoso") is None


def test_insight_is_written_beside_the_hub_and_read_back(customers, vault):  # noqa: F811
    hub_before = contoso(vault, "Contoso.md").read_text("utf-8")
    saved = customers.set_insight("Contoso", TERMS)

    assert saved["terms"][0]["percent"] == 3
    assert saved["terms"][1] == {"model": "yearly", "start": "2026-07-01", "amount": 20000, "billing_day": 5}
    assert "targets" not in saved
    assert saved["note"] == "Signed in March."
    assert customers.insight("Contoso") == saved
    assert contoso(vault, "Contoso.md").read_text("utf-8") == hub_before

    text = contoso(vault, "Contoso - Insight.md").read_text("utf-8")
    assert text.startswith('---\ntype: "Insight"\nname: "Contoso Insight"\nparent: "[[Contoso]]"\n')
    assert "## Data\n\n```json\n" in text
    assert "| yearly | 2026-07-01 |  |  | 20000 |  |  |" in text


def test_an_affiliate_has_its_own_insight(customers, vault):  # noqa: F811
    customers.set_insight("Contoso Labs", {"terms": [{"model": "upfront", "start": "2026-02-01", "amount": 1}]})
    assert (vault / "Work/Customers/Contoso/Affiliates/Contoso Labs/Contoso Labs - Insight.md").exists()
    assert customers.insight("Contoso") is None


def test_none_removes_the_note(customers, vault):  # noqa: F811
    customers.set_insight("Contoso", TERMS)
    assert customers.set_insight("Contoso", None) is None
    assert not contoso(vault, "Contoso - Insight.md").exists()
    assert customers.set_insight("Contoso", None) is None


@pytest.mark.parametrize("bad, message", [
    ({"terms": [{"start": "2026-01-01"}]}, "model"),
    ({"terms": [{"model": "yearly", "start": "01/02/2026"}]}, "date"),
    ({"terms": [{"model": "yearly", "start": "2026-02-30"}]}, "date"),
    ({"terms": [{"model": "yearly", "start": "2026-05-01", "end": "2026-04-01"}]}, "before"),
    ({"terms": [{"model": "percentage", "start": "2026-01-01", "percent": "3"}]}, "number"),
    ({"terms": [{"model": "percentage", "start": "2026-01-01", "subtract_credits": "yes"}]}, "true or false"),
    ({"terms": "x"}, "list"),
    ({"targets": {"2026": 1}}, "not known"),
    ({"colour": "red"}, "not known"),
])
def test_a_bad_shape_is_refused_and_nothing_is_written(customers, vault, bad, message):  # noqa: F811
    with pytest.raises(OpportunityError, match=message):
        customers.set_insight("Contoso", bad)
    assert not contoso(vault, "Contoso - Insight.md").exists()


def test_a_hand_broken_json_block_is_reported_not_read_as_empty(customers, vault):  # noqa: F811
    customers.set_insight("Contoso", TERMS)
    path = contoso(vault, "Contoso - Insight.md")
    path.write_text(path.read_text("utf-8").replace('"note"', 'note'), encoding="utf-8")
    with pytest.raises(OpportunityError, match="does not parse"):
        customers.insight("Contoso")


def test_an_unknown_hub_is_not_found(customers):
    with pytest.raises(OpportunityNotFound):
        customers.insight("Nobody")
    with pytest.raises(OpportunityNotFound):
        customers.set_insight("Nobody", TERMS)
