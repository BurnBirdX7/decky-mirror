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

See detailed description at [Upstream API](#upstream-api). Mirror's response always contains `artifact` string:

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
`base64url` is padded URL-safe Base64 of the original URL's UTF-8 bytes.
Decoding validates URL syntax; IP literals are checked before connecting, and
hostnames are checked through their resolved DNS addresses.
Resources must use absolute HTTP(S) URLs without embedded credentials.
Only public destinations are allowed: loopback, private, link-local, unspecified,
multicast and reserved IPv4/IPv6 addresses are blocked. DNS lookups are rejected
if any result is non-public, and connections use the validated numeric addresses.
Each resource redirect is checked before connecting; up to 10 redirects are followed.

Mirror errors:

| Status | Cause |
| --- | --- |
| `400` | Invalid resource encoding, hash or URL syntax. |
| `403` | Non-public destination, including DNS results or redirects. |
| `422` | Invalid query parameters. |
| `502` | Invalid upstream catalogue, connection failure, missing redirect destination or more than 10 redirects. |
| `504` | Upstream timeout (30 seconds per request). |

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


# Upstream API

## GET `/plugins`

URL: `https://${TARGET_STORE_DOMAIN}/plugins`

Request header: `X-Decky-Version: <installed Decky version>` (sent by Decky).

Optional query parameters:

| Parameter        | Type                                                   | Default |
|------------------|--------------------------------------------------------|---------|
| `query`          | string                                                 | `""`    |
| `tags`           | repeated strings; comma-separated values also accepted | `[]`    |
| `hidden`         | boolean                                                | `false` |
| `sort_by`        | `name`, `date`, or `downloads`                         | unset   |
| `sort_direction` | `asc` or `desc`                                        | `desc`  |

Response: `200 OK`, `Content-Type: application/json`, an array of plugin objects:

```typescript
{
  id: number;
  name: string;
  author: string;
  description: string;
  tags: string[];
  visible: boolean;
  image_url: string;
  downloads: number | null;
  updates: number | null;
  created: string | null; // ISO 8601
  updated: string | null; // ISO 8601
  versions: {
    name: string;
    hash: string;        // ZIP SHA-256, hexadecimal
    created: string;     // ISO 8601
    downloads: number;
    updates: number;
    artifact?: string | null; // Supported by Decky; not declared in the official store schema
  }[];
}
```

Decky treats `versions[0]` as the latest version. An absent or `null` artifact
falls back to the baked-in URL `https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/${hash}.zip`.
The URL in `image_url` is used directly.

Sources: [store routes](https://github.com/SteamDeckHomebrew/decky-plugin-store/blob/main/plugin_store/api/__init__.py),
[response schema](https://github.com/SteamDeckHomebrew/decky-plugin-store/blob/main/plugin_store/api/models/base.py),
[Decky client](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/frontend/src/store.tsx).

## POST `/plugins/{plugin_name}/versions/{version_name}/increment`

URL: `https://${TARGET_STORE_DOMAIN}/plugins/{plugin_name}/versions/{version_name}/increment`

Path parameters are the catalogue plugin name and version name. Query parameter
`isUpdate` is a boolean with server default `true`; Decky sends whether the
plugin was already installed. The request has no body.

Responses:

- `200 OK` — recorded; empty body.
- `404 Not Found` — plugin/version not found.
- `429 Too Many Requests` — rate limit reached.

Sources: [store route](https://github.com/SteamDeckHomebrew/decky-plugin-store/blob/main/plugin_store/api/__init__.py),
[Decky installer](https://github.com/SteamDeckHomebrew/decky-loader/blob/main/backend/decky_loader/browser.py).
