# Decky Store Mirror

Minimal FastAPI server skeleton. All application endpoints return HTTP 501
with `{"detail":"Not implemented"}`. No upstream requests or caching are implemented.

## Requirements

- uv
- Python 3.14.8 (uv can install the pinned interpreter automatically)

## Install and run

```sh
uv sync --locked
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Dependencies are locked in `uv.lock`; the local environment lives in `.venv`.
This service does not require a package build step.

## Endpoints

- `GET /plugins`
- `GET /versions/{hash}.zip`
- `GET /artifact_images/{filename}`
- `POST /plugins/{plugin_name}/versions/{version_name}/increment`

Interactive API documentation: http://127.0.0.1:8000/docs
OpenAPI schema: http://127.0.0.1:8000/openapi.json

Catalogue CORS allows `https://steamloopback.host`, `GET`, and the
`X-Decky-Version` header. Preflight requests are handled by the CORS middleware.

