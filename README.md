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

## HTTPS with Caddy

Run Uvicorn on `127.0.0.1:8000` and use Caddy as the public HTTPS entry point.
Save the following configuration as `Caddyfile`:

```caddyfile
{$DECKY_DOMAIN} {
    reverse_proxy 127.0.0.1:8000
}
```

Set the domain through the environment and start Caddy (POSIX shell example):

```sh
export DECKY_DOMAIN=decky.example.com
export PUBLIC_BASE_URL="https://${DECKY_DOMAIN}"
caddy run --config ./Caddyfile --adapter caddyfile
```

Start Uvicorn separately using the command above. Caddy reads `DECKY_DOMAIN`
from its process environment when loading the configuration. The domain must
resolve to the server, with ports 80 and 443 reachable for automatic HTTPS.
See [Caddy environment variables](https://caddyserver.com/docs/caddyfile/concepts#environment-variables)
and [automatic HTTPS](https://caddyserver.com/docs/automatic-https).

`PUBLIC_BASE_URL` is the intended application setting for public download and
image URLs; the current endpoint skeleton does not read it yet. Pass it to the
application's environment when URL generation is implemented. The Decky custom
store address is `${PUBLIC_BASE_URL}/plugins`.

Both processes can receive variables from a shared environment configuration.
Service management and system integration are deployment-specific.

