# Decky Store Mirror

FastAPI mirror of the Decky Store API. Substitutes catalogue resource URLs and
streams images and archives from upstream without resource caching.

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

## API structure

Interactive API documentation: http://127.0.0.1:8000/docs
OpenAPI schema: http://127.0.0.1:8000/openapi.json

Catalogue CORS allows `https://steamloopback.host`, `GET`, and the
`X-Decky-Version` header. Preflight requests are handled by the CORS middleware.

### Store API

Mirrors the Decky Store API at `TARGET_STORE_DOMAIN`:

- `GET /plugins` — relay the catalogue and substitute resource URLs.
- `POST /plugins/{plugin_name}/versions/{version_name}/increment` — relay installation statistics.

See detailed description at [UPSTREAM.md](UPSTREAM.md). Mirror's response always contains `artifact` string:

| Upstream value                       | Mirror URL                                        |
|--------------------------------------|---------------------------------------------------|
| `artifact` missing or `null`         | `https://${DOMAIN}/resources/hash/${hash}`        |
| `artifact` contains an explicit URL  | `https://${DOMAIN}/resources/base64/${base64url}` |
| `image_url` contains an explicit URL | `https://${DOMAIN}/resources/base64/${base64url}` |

An empty artifact string is invalid; it does not trigger the hash fallback.
Images have no hash-derived fallback.

### Resources API

- `GET /resources/hash/{hash}` — retrieve `https://${TARGET_CDN_DOMAIN}/file/steam-deck-homebrew/versions/${hash}.zip`.
- `GET /resources/base64/{base64url}` — decode the complete original URL and relay that resource.

Upstream HTTP statuses and relevant response headers are relayed. Failures after
resource streaming begins terminate the stream; the upstream response is closed.


## Environment variables

All three variables are required. The Python application loads `.env` from the project directory; existing environment variables take precedence. Domain values are hostnames without a scheme or path.

| Variable              | Example                | Purpose                                  |
|-----------------------|------------------------|------------------------------------------|
| `DOMAIN`              | `decky.example.com`    | Public mirror domain, also used by Caddy |
| `TARGET_STORE_DOMAIN` | `plugins.deckbrew.xyz` | Upstream Decky store domain              |
| `TARGET_CDN_DOMAIN`   | `cdn.tzatzikiweeb.moe` | Upstream CDN domain                      |

Example `.env`:
```dotenv
DOMAIN=decky.example.com
TARGET_STORE_DOMAIN=plugins.deckbrew.xyz
TARGET_CDN_DOMAIN=cdn.tzatzikiweeb.moe
```

Caddy reads `DOMAIN` from its process environment; it does not load the application's `.env` automatically.

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
