# Surveillance RBAC

| Role | View | Review/assign/escalate | Request/approve restriction | Resolve critical |
|---|---:|---:|---:|---:|
| surveillance_viewer | yes | no | no | no |
| surveillance_analyst | yes | yes | no | no |
| surveillance_manager | yes | yes | maker/checker | yes |
| platform_admin | yes | yes | maker/checker | policy-authorized |
| support roles/customer | no | no | no | no |

All resource queries are server-scoped to the authenticated tenant. Arbitrary tenant headers and resource IDs cannot select another tenant.
