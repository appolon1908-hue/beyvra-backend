# Operational endpoint inventory

All paths are unique. Public paths are safe/read-only except readiness mechanics; operator mutations require authentication, scoped RBAC, reason codes, audit, and the documented maker/checker rule.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Process liveness |
| GET | `/ready` | Required dependency readiness |
| GET | `/api/v1/system/status` | Customer-safe aggregate mode |
| GET | `/api/v1/system/capabilities` | Customer-safe capabilities; real value false |
| GET | `/api/v1/operator/system/health` | Service health evidence |
| GET | `/api/v1/operator/system/dependencies` | Dependency policy/evidence |
| GET | `/api/v1/operator/system/slos[/{code}]` | Versioned SLO definitions |
| GET | `/api/v1/operator/system/error-budgets` | Calculated budgets |
| GET | `/api/v1/operator/system/capacity[/{service}]` | Tested capacity claims |
| GET | `/api/v1/operator/system/mode` | Resolved operational mode |
| GET | `/api/v1/operator/system/kill-switches` | Switch state |
| POST | `/api/v1/operator/system/kill-switches/{code}/activate` | Emergency activation |
| POST | `/api/v1/operator/system/kill-switches/{code}/request-deactivation` | Maker request |
| POST | `/api/v1/operator/system/kill-switches/{code}/approve-deactivation` | Checker approval |
| GET | `/api/v1/operator/system/release[/{id}]` | Immutable candidate identity |
| GET | `/api/v1/operator/system/release/{id}/evidence` | Immutable evidence manifest |
| GET | `/api/v1/operator/system/deployments` | Read-only deployment plans |
| GET | `/api/v1/operator/system/configuration` | Safe configuration metadata |
| GET | `/api/v1/operator/system/feature-flags` | Evaluated fail-closed flags |
| GET | `/api/v1/operator/system/incidents[/{id}]` | Incident records |
| POST | `/api/v1/operator/system/incidents/{id}/acknowledge` | Controlled transition |
| POST | `/api/v1/operator/system/incidents/{id}/resolve` | Controlled transition |
| GET | `/api/v1/operator/system/reconciliation` | Latest exact-candidate report |
| POST | `/api/v1/operator/system/reconciliation/run` | Narrow audited reconciliation |

There is no generic action, admin, toggle, production deployment, live execution, live settlement, or live treasury endpoint.
