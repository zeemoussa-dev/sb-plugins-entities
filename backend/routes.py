"""The Entities registry's HTTP surface. The host mounts it under `/plugins/entities/`;
paths, bodies and status codes match the framework's former `/vault/entities`."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .accounts import AccountConflict, Accounts
from .opportunities import OpportunityError, OpportunityNotFound, VaultNotReady
from .registry import DuplicateEntityError, EntitiesRegistry, EntityNotFoundError


class CreateEntityBody(BaseModel):
    name: str
    section: str
    domain: str = ""
    aliases: str = ""
    affiliate_of: str = ""


class UpdateEntityBody(BaseModel):
    name: str | None = None
    section: str | None = None
    aliases: str | None = None
    affiliate_of: str | None = None
    domain: str | None = None
    ignore: bool | None = None


class SectionTextBody(BaseModel):
    text: str
    # The text the page loaded, so an edit made meanwhile in Obsidian is not overwritten.
    previous: str


class CaptureBody(BaseModel):
    title: str = ""
    text: str


class NewCustomerBody(BaseModel):
    name: str
    aliases: list[str] = []


def _account_call(call):
    try:
        return call()
    except OpportunityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccountConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OpportunityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VaultNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _signed_in_name(request: Request) -> str:
    """Who is signed in, for a capture's "Added by". The host's sign-in puts the
    caller on `request.state.identity`; the Plugin API has no call for it yet, so
    read it defensively -- a framework that renames it gives "someone", not a 500."""
    user = getattr(getattr(request.state, "identity", None), "user", None)
    return getattr(user, "display_name", "") or getattr(user, "username", "") or ""


def build_router(registry: EntitiesRegistry, accounts: Accounts) -> APIRouter:
    router = APIRouter()

    @router.get("/accounts")
    def list_accounts() -> dict:
        return _account_call(accounts.list)

    @router.post("/accounts/customer")
    def post_customer(body: NewCustomerBody) -> dict:
        return _account_call(lambda: accounts.create_customer(body.name, body.aliases))

    @router.get("/accounts/{kind}/{stem}")
    def get_account(kind: str, stem: str) -> dict:
        return _account_call(lambda: accounts.detail(kind, stem))

    @router.get("/accounts/{kind}/{stem}/cost")
    def get_account_cost(kind: str, stem: str) -> dict:
        return _account_call(lambda: accounts.cost(kind, stem))

    @router.put("/accounts/{kind}/{stem}/personal-notes")
    def put_personal_notes(kind: str, stem: str, body: SectionTextBody) -> dict:
        return {"text": _account_call(lambda: accounts.set_personal_notes(kind, stem, body.text, body.previous))}

    @router.post("/accounts/{kind}/{stem}/captures-note")
    def post_captures_note(kind: str, stem: str) -> dict:
        return _account_call(lambda: accounts.create_captures_note(kind, stem))

    @router.post("/accounts/{kind}/{stem}/captures")
    def post_capture(kind: str, stem: str, body: CaptureBody, request: Request) -> dict:
        return _account_call(lambda: accounts.add_capture(kind, stem, body.title, body.text, _signed_in_name(request)))

    @router.get("/entities")
    def list_entities() -> dict:
        return {"entities": registry.list_entities()}

    @router.post("/entities")
    def create_entity(body: CreateEntityBody) -> dict:
        try:
            return registry.create_entity(body.name, body.section, body.domain, body.aliases, body.affiliate_of)
        except DuplicateEntityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/entities/{name}")
    def update_entity(name: str, body: UpdateEntityBody) -> dict:
        try:
            return registry.update_entity(name, body.model_dump(exclude_none=True))
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DuplicateEntityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/entities/{name}")
    def delete_entity(name: str) -> dict:
        try:
            registry.delete_entity(name)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": True}

    return router
