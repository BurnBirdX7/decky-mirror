# Upstream API

API provided by Decky Plugin Store

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
    artifact: string | null; // Supported by Decky; not declared in the official store schema
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
