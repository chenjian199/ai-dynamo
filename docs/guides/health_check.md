<!--
SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Dynamo Health Checks

## Overview

Dynamo provides health check and liveness HTTP endpoints for each component which
can be used to configure startup, liveness and readiness probes in
orchestration frameworks such as Kubernetes.

## Frontend Liveness Check

The frontend liveness endpoint reports a status of `live` as long as
the service is running.

> **Note**: Frontend liveness doesn't depend on worker health or liveness only on the Frontend service itself.

### Example Request

```
curl -s localhost:8080/live -q | jq
```

### Example Response

```
{
  "message": "Service is live",
  "status": "live"
}
```

## Frontend Health Check

The frontend health endpoint reports a status of `healthy` as long as
the service is running.  Once workers have been registered, the
`health` endpoint will also list registered endpoints and instances.

> **Note**: Frontend liveness doesn't depend on worker health or liveness only on the Frontend service itself.

### Example Request

```
curl -v localhost:8080/health -q | jq
```

### Example Response

Before workers are registered:

```
HTTP/1.1 200 OK
content-type: application/json
content-length: 72
date: Wed, 03 Sep 2025 13:31:44 GMT

{
  "instances": [],
  "message": "No endpoints available",
  "status": "unhealthy"
}
```

After workers are registered:

```
HTTP/1.1 200 OK
content-type: application/json
content-length: 609
date: Wed, 03 Sep 2025 13:32:03 GMT

{
  "endpoints": [
    "dyn://dynamo.backend.generate"
  ],
  "instances": [
    {
      "component": "backend",
      "endpoint": "clear_kv_blocks",
      "instance_id": 7587888160958628000,
      "namespace": "dynamo",
      "transport": {
        "nats_tcp": "dynamo_backend.clear_kv_blocks-694d98147d54be25"
      }
    },
    {
      "component": "backend",
      "endpoint": "generate",
      "instance_id": 7587888160958628000,
      "namespace": "dynamo",
      "transport": {
        "nats_tcp": "dynamo_backend.generate-694d98147d54be25"
      }
    },
    {
      "component": "backend",
      "endpoint": "load_metrics",
      "instance_id": 7587888160958628000,
      "namespace": "dynamo",
      "transport": {
        "nats_tcp": "dynamo_backend.load_metrics-694d98147d54be25"
      }
    }
  ],
  "status": "healthy"
}
```

## Worker Liveness and Health Check

Health checks for components other than the frontend are enabled
selectively based on environment variables. If a health check for a
component is enabled the starting status can be set along with the set
of endpoints that are required to be served before the component is
declared `ready`.

Once all endpoints declared in `DYN_SYSTEM_USE_ENDPOINT_HEALTH_STATUS`
are served the component transitions to a `ready` state until the
component is shutdown. The endpoints return HTTP status code of `HTTP/1.1 503 Service Unavailable`
when initializing and HTTP status code `HTTP/1.1 200 OK` once ready.

> **Note**: Both /live and /ready return the same information

### Environment Variables for Enabling Health Checks

| **Environment Variable** | **Description**     | **Example Settings**                             |
| -------------------------| ------------------- | ------------------------------------------------ |
| `DYN_SYSTEM_ENABLED`     | Enables the system status server.                                            | `true`, `false`                           |
| `DYN_SYSTEM_PORT`        | Specifies the port for the system status server.                              | `9090`                                   |
| `DYN_SYSTEM_STARTING_HEALTH_STATUS`     | Sets the initial health status of the system (ready/not ready).                | `ready`, `notready`      |
| `DYN_SYSTEM_HEALTH_PATH`                | Custom path for the health endpoint.                                         | `/custom/health`           |
| `DYN_SYSTEM_LIVE_PATH`                   | Custom path for the liveness endpoint.                                       | `/custom/live`            |
| `DYN_SYSTEM_USE_ENDPOINT_HEALTH_STATUS` | Specifies endpoints to check for determining overall system health status.    | `["generate"]`            |

### Example Environment Setting

```
export DYN_SYSTEM_ENABLED="true"
export DYN_SYSTEM_STARTING_HEALTH_STATUS="notready"
export DYN_SYSTEM_USE_ENDPOINT_HEALTH_STATUS="[\"generate\"]"
export DYN_SYSTEM_PORT=9090
```

#### Example Request

```
curl -v localhost:9090/health | jq
```

#### Example Response
Before endpoints are being served:

```
HTTP/1.1 503 Service Unavailable
content-type: text/plain; charset=utf-8
content-length: 96
date: Wed, 03 Sep 2025 13:42:39 GMT

{
  "endpoints": {
    "generate": "notready"
  },
  "status": "notready",
  "uptime": {
    "nanos": 313803539,
    "secs": 12
  }
}
```

After endpoints are being served:

```
HTTP/1.1 200 OK
content-type: text/plain; charset=utf-8
content-length: 139
date: Wed, 03 Sep 2025 13:42:45 GMT

{
  "endpoints": {
    "clear_kv_blocks": "ready",
    "generate": "ready",
    "load_metrics": "ready"
  },
  "status": "ready",
  "uptime": {
    "nanos": 356504530,
    "secs": 18
  }
}
```

## Related Documentation

- [Distributed Runtime Architecture](../architecture/distributed_runtime.md)
- [Dynamo Architecture Overview](../architecture/architecture.md)
- [Backend Guide](backend.md)
