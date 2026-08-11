# Financial trust boundary

```plantuml
@startuml
actor User
component "Beyvra frontend" as UI
component "Application API\nfinancial_boundary" as APP
component "FinancialServiceClient\nHTTPS + mTLS + scope + v1" as CLIENT
component "Financial Service" as FS
database "Financial PostgreSQL" as FDB
component "Custody/payment provider" as PROVIDER
User --> UI
UI --> APP : authenticated /api/v1
APP --> CLIENT : future approved delegation
CLIENT --> FS : internal/v1 only
FS --> FDB
FS --> PROVIDER : separately approved only
APP -[#red,dashed]-> FDB : DENIED
UI -[#red,dashed]-> FS : DENIED
UI -[#red,dashed]-> PROVIDER : DENIED
@enduml
```

Financial Service is sole financial authority. Application PostgreSQL may hold request metadata, inbox/outbox, incidents, and projections, never authoritative balances or effects. The legacy local ledger is quarantined and is not a permissible future activation path. No Financial database hostname, owner, migrator, service-role credential, or SQL appears in application configuration.
