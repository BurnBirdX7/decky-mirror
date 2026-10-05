from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Decky Mirror")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://steamloopback.host"],
    allow_methods=["GET"],
    allow_headers=["X-Decky-Version"],
)


@app.get("/plugins")
async def plugins(
    query: str = "",
    tags: Annotated[list[str], Query()] = [],
    hidden: bool = False,
    sort_by: Literal["name", "date", "downloads"] | None = None,
    sort_direction: Literal["asc", "desc"] = "desc",
    decky_version: Annotated[str | None, Header(alias="X-Decky-Version")] = None,
):
    raise HTTPException(status_code=501, detail="Not implemented")


@app.get("/versions/{hash}.zip")
async def version_archive(hash: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@app.get("/artifact_images/{filename}")
async def artifact_image(filename: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@app.post("/plugins/{plugin_name}/versions/{version_name}/increment")
async def increment(plugin_name: str, version_name: str, isUpdate: bool = True):
    raise HTTPException(status_code=501, detail="Not implemented")
