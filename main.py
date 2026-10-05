from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import constants

app = FastAPI(title="Decky Mirror")
# The IDE reports a protocol mismatch for FastAPI's documented middleware API.
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://steamloopback.host"],
    allow_methods=["GET"],
    allow_headers=["X-Decky-Version"],
)

store_api = APIRouter(tags=["Store API"])
resources_api = APIRouter(prefix="/resources", tags=["Resources API"])


@store_api.get("/plugins")
async def plugins(
    query: str = "",
    tags: list[str] = Query(default_factory=list),
    hidden: bool = False,
    sort_by: Literal["name", "date", "downloads"] | None = None,
    sort_direction: Literal["asc", "desc"] = "desc",
    decky_version: Annotated[str | None, Header(alias="X-Decky-Version")] = None,
):
    """Mirror the catalogue, rewriting artifact and image URLs to resource URLs."""
    raise HTTPException(status_code=501, detail="Not implemented")


@store_api.post("/plugins/{plugin_name}/versions/{version_name}/increment")
async def increment(plugin_name: str, version_name: str, isUpdate: bool = True):
    """Relay installation statistics to the upstream store."""
    raise HTTPException(status_code=501, detail="Not implemented")


@resources_api.get("/hash/{hash}")
async def resource_by_hash(hash: str):
    """Relay the archive at the upstream CDN's hash-derived URL."""
    raise HTTPException(status_code=501, detail="Not implemented")


@resources_api.get("/base64/{base64url}")
async def resource_by_base64(base64url: str):
    """Relay an explicit resource URL encoded as unpadded URL-safe Base64."""
    raise HTTPException(status_code=501, detail="Not implemented")


app.include_router(store_api)
app.include_router(resources_api)
