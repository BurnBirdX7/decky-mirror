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

## Environment variables

Domain values are hostnames without a scheme or path.

| Variable              | Example                | Purpose                                  |
|-----------------------|------------------------|------------------------------------------|
| `DOMAIN`              | `decky.example.com`    | Public mirror domain, also used by Caddy |
| `TARGET_STORE_DOMAIN` | `plugins.deckbrew.xyz` | Upstream Decky store domain              |
| `TARGET_CDN_DOMAIN`   | `cdn.tzatzikiweeb.moe` | Upstream CDN domain                      |

```bash
# example
export DOMAIN=decky.example.com
export TARGET_STORE_DOMAIN=plugins.deckbrew.xyz
export TARGET_CDN_DOMAIN=cdn.tzatzikiweeb.moe
```

## HTTPS with Caddy

Run Uvicorn on `127.0.0.1:8000` and use Caddy as the public HTTPS entry point.
Save the following configuration as `Caddyfile`:

```caddyfile
{$DOMAIN} {
    reverse_proxy 127.0.0.1:8000
}
```

With `DOMAIN` set in its environment, start Caddy:

```sh
caddy run --config ./Caddyfile --adapter caddyfile
```

See [Caddy environment variables](https://caddyserver.com/docs/caddyfile/concepts#environment-variables)
and [automatic HTTPS](https://caddyserver.com/docs/automatic-https).
