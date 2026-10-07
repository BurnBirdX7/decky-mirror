from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import constants
from .catalogue import (
    build_archive_url,
    decode_resource_url,
    substitute_catalogue_resource_urls,
)
from .errors import MirrorError
from .rate_limit import RATE_LIMIT, limiter
from .upstream import (
    ResourceStreamingResponse,
    UpstreamClient,
    get_upstream_client,
    lifespan,
)


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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
@limiter.limit(RATE_LIMIT)
async def plugins(
    request: Request,
    parameters: Annotated[CatalogueQuery, Query()],
    client: Client,
    decky_version: Annotated[str | None, Header(alias="X-Decky-Version")] = None,
) -> Response:
    """Mirror the catalogue, substituting artifact and image URLs with resource URLs."""
    response = await client.get_catalogue(parameters.to_parameters(), decky_version)
    if response.status != 200:
        return response.to_response()
    return JSONResponse(substitute_catalogue_resource_urls(response.content, constants.DOMAIN))


# noinspection PyPep8Naming
@store_api.post("/plugins/{plugin_name}/versions/{version_name}/increment")
@limiter.limit(RATE_LIMIT)
async def increment(
    request: Request, plugin_name: str, version_name: str, client: Client, isUpdate: bool = True
) -> Response:
    """Relay installation statistics to the upstream store."""
    response = await client.post_install_increment(plugin_name, version_name, isUpdate)
    return response.to_response()


@resources_api.get("/hash/{hash}")
@limiter.limit(RATE_LIMIT)
async def resource_by_hash(request: Request, hash: str, client: Client) -> StreamingResponse:
    """Relay the archive at the upstream CDN's hash-derived URL."""
    destination_url = build_archive_url(hash, constants.TARGET_CDN_DOMAIN)
    return ResourceStreamingResponse(await client.get_resource_with_redirects(destination_url))


@resources_api.get("/base64/{base64url}")
@limiter.limit(RATE_LIMIT)
async def resource_by_base64(request: Request, base64url: str, client: Client) -> StreamingResponse:
    """Relay an explicit resource URL encoded as padded URL-safe Base64."""
    destination_url = decode_resource_url(base64url)
    return ResourceStreamingResponse(await client.get_resource_with_redirects(destination_url))


app.include_router(store_api)
app.include_router(resources_api)
