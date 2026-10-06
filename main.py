from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

import constants
from catalogue import make_archive_url, decode_resource_url, rewrite_catalogue
from errors import MirrorError
from upstream import UpstreamClient, get_upstream_client, lifespan, resource_response


class CatalogueQuery(BaseModel):
    query: str = ""
    tags: list[str] = Field(default_factory=list)
    hidden: bool = False
    sort_by: Literal["name", "date", "downloads"] | None = None
    sort_direction: Literal["asc", "desc"] = "desc"

    def to_parameters(self) -> dict[str, str | list[str]]:
        parameters: dict[str, str | list[str]] = self.model_dump(exclude_none=True)
        parameters["hidden"] = str(self.hidden).lower()
        return parameters


Client = Annotated[UpstreamClient, Depends(get_upstream_client)]
app = FastAPI(title="Decky Mirror", lifespan=lifespan)
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


@app.exception_handler(MirrorError)
async def handle_mirror_error(request: Request, error: MirrorError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=error.status_code)


@store_api.get("/plugins")
async def plugins(
    parameters: Annotated[CatalogueQuery, Query()],
    client: Client,
    decky_version: Annotated[str | None, Header(alias="X-Decky-Version")] = None,
) -> Response:
    """Mirror the catalogue, rewriting artifact and image URLs to resource URLs."""
    response = await client.fetch_catalogue(parameters.to_parameters(), decky_version)
    if response.status != 200:
        return response.to_response()
    return JSONResponse(rewrite_catalogue(response.content, constants.DOMAIN))


@store_api.post("/plugins/{plugin_name}/versions/{version_name}/increment")
async def increment(
    plugin_name: str, version_name: str, client: Client, isUpdate: bool = True
) -> Response:
    """Relay installation statistics to the upstream store."""
    response = await client.record_install(plugin_name, version_name, isUpdate)
    return response.to_response()


@resources_api.get("/hash/{hash}")
async def resource_by_hash(hash: str, client: Client) -> StreamingResponse:
    """Relay the archive at the upstream CDN's hash-derived URL."""
    url = make_archive_url(hash, constants.TARGET_CDN_DOMAIN)
    return resource_response(await client.open_resource(url))


@resources_api.get("/base64/{base64url}")
async def resource_by_base64(base64url: str, client: Client) -> StreamingResponse:
    """Relay an explicit resource URL encoded as unpadded URL-safe Base64."""
    return resource_response(await client.open_resource(decode_resource_url(base64url)))


app.include_router(store_api)
app.include_router(resources_api)
