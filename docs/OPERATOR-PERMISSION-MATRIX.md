# Operator permission matrix

| Role family | View | Create/update | Approve | Freeze | Unfreeze | Export | Override |
|---|---|---|---|---|---|---|---|
| support viewer/agent/manager | masked support | agent/manager | no | no | no | manager, safe | no |
| security viewer/analyst/manager | security | analyst/manager cases | manager, independent | manager emergency | manager checker | manager, safe | governed request |
| compliance viewer/analyst/manager | compliance | analyst restrictions | manager, independent | no | no | manager, safe | governed request |
| financial viewer/operations/manager | safe financial | requests only | manager, independent | no | no | manager, safe | Financial Service request |
| operations viewer/engineer/manager | system state | incident/halt request | manager, independent | no | no | operational only | no compliance override |
| platform_admin | cross-domain configuration | limited | independent checker still required | policy | independent checker | safe | no self-approval |

All roles are tenant scoped. Normal work does not use unrestricted superuser. Sensitive actions require MFA/step-up, an expiring request, reason, and append-only audit.
