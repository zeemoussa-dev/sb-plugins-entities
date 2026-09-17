"""The Entities registry's HTTP surface. The host mounts it under `/plugins/entities/`;
paths, bodies and status codes match the framework's former `/vault/entities`."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


def build_router(registry: EntitiesRegistry) -> APIRouter:
    router = APIRouter()

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
