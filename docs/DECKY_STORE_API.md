# Decky Store Public Plugin API

Source project: [SteamDeckHomebrew/decky-plugin-store](https://github.com/SteamDeckHomebrew/decky-plugin-store/tree/8c41c90438f4c1c60256a12e3c2472112660914e). Branch: `main`. Commit: `8c41c90438f4c1c60256a12e3c2472112660914e`. Checked: 2026-10-10. This document describes pinned source behavior; deployment behavior was not verified.

Base origin: `https://plugins.deckbrew.xyz`. Scope: public plugin catalog and install/update counters only.

## GET /plugins

### Request

```http
GET /plugins?query=Example&hidden=false&sort_by=name&sort_direction=desc
Accept: application/json
```

**Important headers**

| Header   | Required | Meaning                                        |
|----------|----------|------------------------------------------------|
| `Accept` | No       | `application/json` is suitable for the catalog |

No custom header is required.

**Query parameters**

| Parameter        | Type                           | Required | Default      | Meaning                                                                                          |
|------------------|--------------------------------|----------|--------------|--------------------------------------------------------------------------------------------------|
| `query`          | String                         | No       | Empty string | Case-insensitive substring match against plugin name only                                        |
| `tags`           | Repeated strings               | No       | Empty list   | **Has no effect**. Repeated and comma-separated values are accepted                              |
| `hidden`         | Boolean                        | No       | `false`      | Selects visible plugins when false and _hidden plugins only_ when true                           |
| `sort_by`        | `name`, `date`, or `downloads` | No       | Omitted      | Selects name, earliest version creation time, or aggregate downloads; omission selects plugin ID |
| `sort_direction` | `desc` or `asc`                | No       | `desc`       | `desc` for descending sort, `asc` - for ascending.                                               |

No request body.

**Notes**

`sort_direction` is reversed in the referenced commit; this is reported fixed in the deployed service.

CORS permits the browser origin `https://steamloopback.host`, credentials, all methods and request headers, and exposes all response headers.

### Response

#### 200 - Plugin catalog

**Important headers**

| Header         | Meaning            |
|----------------|--------------------|
| `Content-Type` | `application/json` |

**Schema**

The body is an array of plugin objects. No matches return `[]`.

```typescript
[
  {
    "id": integer,                  // Plugin ID
    "name": string,                 // Plugin name
    "author": string,
    "description": string,
    "tags": [string],               // Ordered by tag text
    "versions": [                   // Ordered by creation time, newest first
      {
        "name": string,             // Version name; semantic-version syntax is not required
        "hash": string,             // Package hash; format is not constrained by the schema
        "created": string,          // Date-time
        "downloads": integer,       // Version download counter
        "updates": integer          // Version update counter
      },
      // ...
    ],
    "visible": boolean,             // Catalog visibility
    "image_url": string,            // Image URL
    "downloads": integer | null,    // Sum of version download counters
    "updates": integer | null,      // Sum of version update counters
    "created": string | null,       // Earliest version creation time (date-time)
    "updated": string | null        // Latest version creation time (date-time)
  },
  // ...
]
```

**Notes**

An empty `versions` array is permitted.

#### 422 - Invalid query parameter

Invalid query parameter values produce FastAPI's standard validation error response. See [FastAPI request validation errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions).

## POST /plugins/{plugin_name}/versions/{version_name}/increment

### Request

```http
POST /plugins/Example/versions/1.0.0/increment?isUpdate=false
```

**Important headers**

| Header             | Required | Meaning                                                                                             |
|--------------------|----------|-----------------------------------------------------------------------------------------------------|
| `cf-connecting-ip` | No       | Used as client IP for rate limiting when present; otherwise the connection's client address is used |

No custom header is required. No `Content-Type` header is needed.

**Path parameters**

| Parameter      | Type   | Required | Meaning                                          |
|----------------|--------|----------|--------------------------------------------------|
| `plugin_name`  | String | Yes      | Exact plugin name from the catalog, URL-encoded  |
| `version_name` | String | Yes      | Exact version name from the catalog, URL-encoded |

**Query parameters**

| Parameter  | Type    | Required | Default | Meaning                                             |
|------------|---------|----------|---------|-----------------------------------------------------|
| `isUpdate` | Boolean | No       | `true`  | True increments updates; false increments downloads |

No request body.

**Notes**

The limit is two successful increments per fixed daily window per plugin name and client IP, shared across all versions and both counter modes. Failed requests do not consume the allowance.

CORS permits the browser origin `https://steamloopback.host`, credentials, all methods and request headers, and exposes all response headers.

### Response

#### 200 - Counter incremented

The requested version's update or download counter was incremented according to `isUpdate`. A subsequent catalog response may not immediately reflect the increment.

#### 404 - Plugin or version not found

No plugin or version matches the supplied names. This response does not consume the allowance.

#### 429 - Rate allowance exhausted

The allowance is exhausted. This response can also occur for an unknown version. No rate-limit or `Retry-After` header is supplied.

#### 422 - Invalid query parameter

Invalid query parameter values produce FastAPI's standard validation error response. See [FastAPI request validation errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions).
