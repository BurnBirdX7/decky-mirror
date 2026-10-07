# Decky Store Mirror

FastAPI mirror of the Decky Store API. Substitutes catalogue resource URLs and
streams images and archives from upstream without resource caching.

## Requirements

- uv
- Python 3.14.8 (uv can install the pinned interpreter automatically)

## Install and run

```sh
uv sync --locked
uv run uvicorn decky_mirror.main:app --host 127.0.0.1 --port 8000
```

Dependencies are locked in `uv.lock`; the local environment lives in `.venv`.
This service does not require a package build step.

Application code is in `decky_mirror/`; tests are in `tests/`.
Run commands from the project root.

To run the tests:

```sh
uv run python -m unittest discover -s tests -t .
```

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

| Upstream value                       | Mirror URL                                                     |
|--------------------------------------|----------------------------------------------------------------|
| `artifact` missing or `null`         | `https://${DOMAIN}/resources/hash/${hash}`                     |
| `artifact` contains an explicit URL  | `https://${DOMAIN}/resources/base64/${base64url}.${signature}` |
| `image_url` contains an explicit URL | `https://${DOMAIN}/resources/base64/${base64url}.${signature}` |

An empty artifact string is invalid; it does not trigger the hash fallback.
Images have no hash-derived fallback.

### Resources API

- `GET /resources/hash/{hash}` — retrieve `https://${TARGET_CDN_DOMAIN}/file/steam-deck-homebrew/versions/${hash}.zip`.
- `GET /resources/base64/{base64url}.{signature}` — verify the signature, decode the complete original URL and relay that resource.

Catalogue links carry a 22-character signature (HMAC-SHA256 truncated to 16 bytes).
Unsigned links and invalid signatures return `403` without contacting upstream.
Links have no expiry; changing the signing key invalidates previously issued links.
This feature is meant to prevent usage of the mirror as any-destination proxy.

Upstream HTTP statuses and relevant response headers are relayed. Failures after
resource streaming begins terminate the stream; the upstream response is closed.


## Environment variables

All four variables are required. The Python application loads `.env` from the project directory; existing environment variables take precedence. The three domain values are hostnames without a scheme or path.

| Variable               | Example                | Purpose                                                |
|------------------------|------------------------|--------------------------------------------------------|
| `DOMAIN`               | `decky.example.com`    | Public mirror domain, also used by Caddy               |
| `TARGET_STORE_DOMAIN`  | `plugins.deckbrew.xyz` | Upstream Decky store domain                            |
| `TARGET_CDN_DOMAIN`    | `cdn.tzatzikiweeb.moe` | Upstream CDN domain                                    |
| `RESOURCE_SIGNING_KEY` | `random`               | Resource link signing secret or random key per process |

Example `.env`:
```dotenv
DOMAIN=decky.example.com
TARGET_STORE_DOMAIN=plugins.deckbrew.xyz
TARGET_CDN_DOMAIN=cdn.tzatzikiweeb.moe
RESOURCE_SIGNING_KEY=random
```

Set `RESOURCE_SIGNING_KEY=random` to generate a new key once per process start;
previous links stop working after a restart and clients must refresh the catalogue.
Any other nonempty value is used verbatim as a persistent UTF-8 secret, keeping
links valid across restarts while that key remains unchanged.

Caddy reads `DOMAIN` from its process environment; it does not load the application's `.env` automatically.

## HTTPS with Caddy

Run Uvicorn on `127.0.0.1:8000` and use Caddy as the public HTTPS entry point.
For a systemd service, use the following entries in its `[Service]` section,
replacing `/opt/decky-mirror` with the project directory:

```ini
WorkingDirectory=/opt/decky-mirror
ExecStart=/opt/decky-mirror/.venv/bin/uvicorn decky_mirror.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

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
