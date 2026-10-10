# API used by Decky Loader

This document describes the public plugin requests made by Decky Loader and the response data it consumes.

Source project: [SteamDeckHomebrew/decky-loader](https://github.com/SteamDeckHomebrew/decky-loader). Branch: `main`. Commit: [`75563316f9119ee7e36be7f43885be65e877fad0`](https://github.com/SteamDeckHomebrew/decky-loader/commit/75563316f9119ee7e36be7f43885be65e877fad0). Checked: 2026-10-10.

## Configuring the catalog endpoint

| Channel | Catalog endpoint                       |
|---------|----------------------------------------|
| Default | `https://plugins.deckbrew.xyz/plugins` |
| Testing | `https://testing.deckbrew.xyz/plugins` |
| Custom  | The configured `store_url`             |

The custom URL is the **complete catalog endpoint**, including its path. The increment endpoint has no separate setting.

## Forming endpoint URLs

Decky uses string concatenation to form **request URLs**. For catalog requests it always adds a `?` after the configured `store_url`.
Consequently, custom catalog URLs containing:
- a query (`?`) or fragment (`#`) produce incorrect endpoint strings for **catalog** and **increment** paths.
- a trailing `/` produce a double slash in the **increment** path.

Archive and image URLs come from catalog data. A present, non-null `artifact` is used directly.
When it is absent or null, Decky uses the version hash as a ZIP filename under the hardcoded CDN base `https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/`, independently of the configured catalog endpoint. An empty string does not trigger this fallback.
Images use `image_url` directly, with no CDN fallback. A `file://` artifact is read locally instead of generating an HTTP request.

## GET — Catalog

### Request

**Request string**: `{store_url}?{query_params}`

No request body is sent.

| Header            | Type   | Meaning                                                                                    |
|-------------------|--------|--------------------------------------------------------------------------------------------|
| `X-Decky-Version` | String | Current Decky Loader version. The only custom header explicitly supplied for this request. |

| Query parameter  | Type                           | Meaning            |
|------------------|--------------------------------|--------------------|
| `sort_by`        | `name`, `date`, or `downloads` | Catalog ordering   |
| `sort_direction` | `asc` or `desc`                | Ordering direction |

The initial browse request sends `sort_by=name&sort_direction=asc`. Changing the sort selection requests the catalog again. Update checks omit both parameters.

### Response

A JSON array of plugin objects is expected. The schema below uses type placeholders and comments; it is not a literal JSON response.

```typescript
[
  {
    "id": number,                   // Plugin identifier.
    "name": string,                 // Plugin name used for installation and matching.
    "author": string,
    "description": string,
    "tags": [string],               // The exact tag "root" triggers a full-access warning.
    "image_url": string,            // Plugin image address.
    "versions": [                   // Latest/default version first.
      { 
        "name": string,             // Version label.
        "hash": string,             // Archive SHA-256 digest.
        "artifact": string | null   // Optional; absent/null selects fallback.
      },
      // ...
    ]
  },
  // ...
]
```

`artifact` is optional. It is absent from the official Store response schema and lets custom stores supply archive URLs.

## POST — Increment stats

### Request

Request string: `{store_url}/{plugin_name}/versions/{version_name}/increment?{query_params}`


| Path parameter | Type   | Meaning                        |
|----------------|--------|--------------------------------|
| Plugin name    | String | The catalog entry's `name`.    |
| Version name   | String | The selected version's `name`. |

| Query parameter | Type                          | Meaning                                                                                                        |
|-----------------|-------------------------------|----------------------------------------------------------------------------------------------------------------|
| `isUpdate`      | Boolean (`True` or `False`)    | Whether the requested plugin was already installed. Reinstalls and downgrades of an existing plugin send `True`. |

No custom headers, explicit content type, or request body are supplied.

The POST is sent after the remote archive download attempt, before archive availability and hash checks, extraction, or installation success. A non-200 archive response can still result in an increment attempt. Local `file://` installations skip it.

### Response

#### 200 - Increment accepted

The client treats status `200` as acceptance and ignores the response body. No body schema or empty-body requirement is imposed. Acceptance does not establish that the plugin was installed successfully.

Other HTTP statuses are logged and installation continues. Transport failures may interrupt installation. The client does not retry this request.


## GET — Plugin archive

### Request

**Request string**: `https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/{hash}.zip` (when `artifact` is absent or null).

| Path parameter | Type   | Meaning                    |
|----------------|--------|----------------------------|
| hash           | String | Hash of a plugin's version |

No custom headers or request body are supplied. The catalog's `X-Decky-Version` header is not added to archive requests.

### Response

#### 200 - Plugin ZIP archive

The entire body is read as archive data. When the supplied `hash` is nonempty, the archive's SHA-256 hexadecimal digest must match it exactly before extraction. An empty hash skips this comparison; a mismatch prevents extraction.

For other HTTP statuses, the client logs the response and does not retain archive data. It can still attempt increment reporting before checking that the archive is missing. A transport failure may stop the operation earlier.

## GET — Plugin image

### Request

Simple GET request for the provided URL.

No custom headers or request body are specified.

### Response

Image data is consumed by the browser for rendering the plugin card. The card does not define a custom status check, response schema, or hash validation for this resource.
