"""The Entities plugin against a stand-in for the Plugin API."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend
from backend.customers import Customers
from backend.matching import CockpitAgentMatcher, tag_slug
from backend.registry import (
    ENTITIES_FILE, DuplicateEntityError, EntitiesRegistry, EntityNotFoundError, parse_entities, render_entities,
)
from backend.routes import build_router

INDEX = {
    "Adnoc": {"stem": "Adnoc", "frontmatter": {"type": "Customer", "name": "Adnoc"}, "tags": ["customer/adnoc"]},
    "Al Ain": {"stem": "Al Ain", "frontmatter": {"type": "Customer", "name": "Al Ain"}, "tags": ["customer/al-ain"]},
    "G42": {"stem": "G42", "frontmatter": {"type": "Partner", "name": "G42"}, "tags": ["partner/g42"]},
    "Some thread": {"stem": "Some thread", "frontmatter": {"type": "Thread"}, "tags": ["customer/adnoc"]},
}


class FakeData:
    def __init__(self):
        self.files = {}

    def read_text(self, path):
        return self.files.get(path)

    def write_text(self, path, content):
        self.files[path] = content


class FakeApi:
    def __init__(self, experts=None, sections=None):
        self.plugin_id = "entities"
        self.data = FakeData()
        self.vault = type("Vault", (), {"index": staticmethod(lambda: dict(INDEX))})()
        self.agents = type("Agents", (), {"list_experts": staticmethod(lambda: list(experts or []))})()
        self.sections = type("Sections", (), {"get": staticmethod(lambda sid: (sections or {}).get(sid))})()
        self.seed_data_files, self.people_folders, self.services = [], [], {}
        self.routers, self.subject_enrichers, self.agent_matchers = [], [], []

    def register_seed_data_file(self, path):
        self.seed_data_files.append(path)

    def register_people_folders(self, folders):
        self.people_folders.extend(folders)

    def provide_service(self, name, service):
        self.services[name] = service

    def register_subject_enricher(self, enricher):
        self.subject_enrichers.append(enricher)

    def register_agent_matcher(self, matcher):
        self.agent_matchers.append(matcher)

    def register_router(self, router):
        self.routers.append(router)


@pytest.fixture()
def api():
    return FakeApi()


@pytest.fixture()
def registry(api):
    return EntitiesRegistry(api)


# -- register -------------------------------------------------------------------


def test_register_wires_every_seam(api):
    backend.register(api)

    assert api.seed_data_files == [ENTITIES_FILE]
    assert api.people_folders == ["Work/Customers", "Work/Partners"]
    assert set(api.services) == {"entities.customers"}
    assert len(api.subject_enrichers) == 1 and len(api.agent_matchers) == 1 and len(api.routers) == 1


# -- registry -------------------------------------------------------------------


def test_a_rendered_registry_parses_back_to_the_same_entries(registry, api):
    registry.create_entity("Adnoc", "customer", domain="adnoc.ae")
    registry.create_entity("G42", "partner", aliases="Group 42")

    content = api.data.files[ENTITIES_FILE]

    assert content.startswith("# Entities\n") and "\n## Partners\n" in content
    assert render_entities(parse_entities(content)) == content


def test_the_file_format_the_discovery_skills_read_is_unchanged(registry, api):
    registry.create_entity("Adnoc", "customer", domain="adnoc.ae")

    assert "### Adnoc\n\n\tCompany Name: Adnoc\n\n\tAliases: \n\n\tAffiliate of: \n\n\tCreated: No\n\n" \
           "\tIgnore: No\n\n\tDomain: adnoc.ae\n\n\tDeleted: No\n\n\n## Partners" in api.data.files[ENTITIES_FILE]


def test_create_list_update_and_soft_delete(registry, api):
    registry.create_entity("Adnoc", "customer")
    updated = registry.update_entity("adnoc", {"name": "ADNOC Group", "section": "partner", "ignore": True})

    assert updated == {"name": "ADNOC Group", "section": "partner", "aliases": "", "affiliate_of": "",
                       "created": False, "ignore": True, "domain": ""}
    registry.delete_entity("ADNOC Group")
    assert registry.list_entities() == []
    assert "Deleted: Yes" in api.data.files[ENTITIES_FILE]


def test_duplicates_unknown_names_and_bad_sections_are_refused(registry):
    registry.create_entity("Adnoc", "customer")
    registry.create_entity("Taqa", "customer")

    with pytest.raises(DuplicateEntityError):
        registry.create_entity(" adnoc ", "partner")
    with pytest.raises(DuplicateEntityError):
        registry.update_entity("Taqa", {"name": "ADNOC"})
    with pytest.raises(EntityNotFoundError):
        registry.delete_entity("Nobody")
    with pytest.raises(ValueError):
        registry.create_entity("X", "vendor")


def test_the_http_surface_matches_the_former_vault_entities_routes(registry):
    app = FastAPI()
    app.include_router(build_router(registry), prefix="/plugins/entities")
    client = TestClient(app)

    assert client.post("/plugins/entities/entities", json={"name": "Adnoc", "section": "customer"}).status_code == 200
    assert client.post("/plugins/entities/entities", json={"name": "Adnoc", "section": "customer"}).status_code == 409
    assert client.post("/plugins/entities/entities", json={"name": "X", "section": "vendor"}).status_code == 400
    assert client.patch("/plugins/entities/entities/Adnoc", json={"domain": "adnoc.ae"}).json()["domain"] == "adnoc.ae"
    assert client.patch("/plugins/entities/entities/Nobody", json={}).status_code == 404
    assert client.get("/plugins/entities/entities").json()["entities"][0]["name"] == "Adnoc"
    assert client.delete("/plugins/entities/entities/Adnoc").json() == {"deleted": True}
    assert client.delete("/plugins/entities/entities/Adnoc").status_code == 200  # soft-deleted rows can still be found
    assert client.get("/plugins/entities/entities").json() == {"entities": []}


# -- customers --------------------------------------------------------------------


def test_the_customer_comes_from_the_hub_note_name_never_a_partner(api):
    customers = Customers(api)

    assert customers.customer_from_tags(["partner/g42", "customer/al-ain"]) == "Al Ain"
    assert customers.customer_from_tags(["partner/g42"]) is None
    assert customers.subject_enricher("email", {}, ["customer/adnoc"]) == {"customer": "Adnoc"}
    assert customers.subject_enricher("email", {}, []) == {}


# -- Cockpit matching --------------------------------------------------------------


def subject(frontmatter=None, tags=()):
    return {"stem": "s", "frontmatter": frontmatter or {}, "tags": list(tags)}


_ADNOC_EXPERT = {"id": "adnoc-expert", "name": "Adnoc Expert", "description": "", "section_id": "customer"}
_SECTIONS = {"customer": {"id": "customer", "name": "Customer", "fallback_agent_id": "customers-hub"}}


def test_a_customer_with_a_dedicated_expert_gets_that_expert_and_no_fallback():
    matcher = CockpitAgentMatcher(FakeApi(experts=[_ADNOC_EXPERT], sections=_SECTIONS))

    assert matcher.match("email", subject(tags=["customer/adnoc"])) == {"experts": ["adnoc-expert"], "fallback_agent_id": None}
    assert matcher.match("meeting", subject({"customer": "Adnoc"})) == {"experts": ["adnoc-expert"], "fallback_agent_id": None}


def test_a_customer_without_a_dedicated_expert_falls_back_to_the_customer_section():
    matcher = CockpitAgentMatcher(FakeApi(experts=[_ADNOC_EXPERT], sections=_SECTIONS))

    assert matcher.match("email", subject(tags=["customer/taqa"])) == {"experts": [], "fallback_agent_id": "customers-hub"}


def test_an_expert_outside_the_customer_section_does_not_count():
    elsewhere = dict(_ADNOC_EXPERT, section_id="technology")
    matcher = CockpitAgentMatcher(FakeApi(experts=[elsewhere], sections=_SECTIONS))

    assert matcher.match("email", subject(tags=["customer/adnoc"]))["experts"] == []


def test_a_subject_without_a_customer_gets_nothing():
    matcher = CockpitAgentMatcher(FakeApi(experts=[_ADNOC_EXPERT], sections=_SECTIONS))

    assert matcher.match("email", subject(tags=["partner/g42"])) == {"experts": [], "fallback_agent_id": None}


def test_the_tag_slug_matches_the_frameworks():
    assert tag_slug("Department of Government Enablement") == "department-of-government-enablement"
    assert tag_slug("Al Ain!") == "al-ain"
    assert tag_slug("***") == "untitled"
