# Execution RBAC

Customer endpoints require authentication and tenant-owned orders. Operator inventory, health, route evidence, unknown outcomes, reconciliation and controls require Django administrator authority. Halt/resume requires a reason and writes audit/outbox evidence. This is a conservative baseline; separate viewer/operator/manager roles and maker/checker approval remain required before any external provider activation.
