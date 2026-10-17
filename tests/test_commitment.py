"""A Customer's signed Azure commitment on its hub note, through `entities.customers`."""
import json
from pathlib import Path

import pytest

from backend import commitment
from backend.customers import Customers
from backend.opportunities import OpportunityError, OpportunityNotFound
from test_opportunities import FakeApi, write

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "customer" / "Template.json"

HUB = (
    '---\ntype: "Customer"\nname: "Contoso"\ndomain: "contoso.example"\n'
    'tags: ["kind/customer", "customer/contoso"]\n---\n\n## Summary\n\nA customer.\n'
)
SIGNED = {"type": "MACC", "amount": 5000000, "currency": "USD", "start": "2026-01-01", "end": "2028-12-31",
          "note": "Signed with a price match", "include_marketplace": True, "subtract_credits": False}


@pytest.fixture()
def vault(tmp_path):
    customers = tmp_path / "Work" / "Customers"
    write(customers / "Contoso" / "Contoso.md", HUB)
    write(customers / "Contoso" / "Affiliates" / "Contoso Labs" / "Contoso Labs.md",
          '---\ntype: "Customer"\naffiliate_of: "Contoso"\nname: "Contoso Labs"\n'
          'tags: ["kind/customer", "customer/contoso-labs"]\n---\n')
    return tmp_path


@pytest.fixture()
def customers(vault):
    return Customers(FakeApi(vault))


def hub_text(vault, *parts):
    return vault.joinpath("Work", "Customers", *parts).read_text(encoding="utf-8")


def test_the_template_names_the_same_keys_and_types():
    root = json.loads(TEMPLATE.read_text(encoding="utf-8"))["root"]

    assert root["frontmatter_enums"]["macc_type"] == commitment.TYPES
    assert all(key in root["frontmatter_rules"][0] for key in commitment.KEYS.values())
    assert not any(key in root["frontmatter_defaults"] for key in commitment.KEYS.values())


def test_a_customer_without_a_commitment_has_none(customers):
    assert customers.commitment("Contoso") is None


def test_set_writes_only_the_macc_keys_and_reads_back(customers, vault):
    result = customers.set_commitment("Contoso", SIGNED)

    assert result == SIGNED
    assert customers.commitment("Contoso") == SIGNED
    assert hub_text(vault, "Contoso", "Contoso.md") == HUB.replace(
        'tags: ["kind/customer", "customer/contoso"]\n',
        'tags: ["kind/customer", "customer/contoso"]\nmacc_type: "MACC"\nmacc_amount: 5000000\n'
        'macc_currency: "USD"\nmacc_start: "2026-01-01"\nmacc_end: "2028-12-31"\n'
        'macc_note: "Signed with a price match"\nmacc_includes_marketplace: true\nmacc_subtracts_credits: false\n')


def test_defaults_fill_what_the_caller_leaves_out(customers):
    result = customers.set_commitment("Contoso Labs", {"type": "Azure Prepayment", "amount": 250000.5,
                                                       "start": "2026-07-01", "end": "2027-06-30"})

    assert result == {"type": "Azure Prepayment", "amount": 250000.5, "currency": "USD", "start": "2026-07-01",
                      "end": "2027-06-30", "note": "", "include_marketplace": True, "subtract_credits": True}


def test_rewriting_replaces_in_place_and_none_clears_every_key(customers, vault):
    customers.set_commitment("Contoso", SIGNED)
    customers.set_commitment("Contoso", {**SIGNED, "amount": 6000000})

    text = hub_text(vault, "Contoso", "Contoso.md")
    assert text.count("macc_amount:") == 1 and "macc_amount: 6000000\n" in text

    assert customers.set_commitment("Contoso", None) is None
    assert hub_text(vault, "Contoso", "Contoso.md") == HUB


def test_a_hand_edited_value_is_read_not_refused(customers, vault):
    path = vault / "Work" / "Customers" / "Contoso" / "Contoso.md"
    write(path, HUB.replace("---\n\n", 'macc_type: "MACC"\nmacc_amount: 1,200,000\n---\n\n', 1))

    assert customers.commitment("Contoso") == {
        "type": "MACC", "amount": 1200000, "currency": "USD", "start": "", "end": "", "note": "",
        "include_marketplace": True, "subtract_credits": True}


def test_a_bad_commitment_or_an_unknown_customer_is_refused_and_nothing_is_written(customers, vault):
    for bad in [
        {**SIGNED, "type": "Discount"},
        {**SIGNED, "amount": "lots"},
        {**SIGNED, "amount": -1},
        {**SIGNED, "amount": True},
        {**SIGNED, "currency": "dollars"},
        {**SIGNED, "start": "2026-13-01"},
        {**SIGNED, "end": "2025-12-31"},
        {**SIGNED, "include_marketplace": "yes"},
        {**SIGNED, "owner": "someone"},
        "MACC",
    ]:
        with pytest.raises(OpportunityError):
            customers.set_commitment("Contoso", bad)
    assert hub_text(vault, "Contoso", "Contoso.md") == HUB
    with pytest.raises(OpportunityNotFound):
        customers.commitment("Nobody")
    with pytest.raises(ValueError):
        customers.set_commitment("../Contoso", SIGNED)
