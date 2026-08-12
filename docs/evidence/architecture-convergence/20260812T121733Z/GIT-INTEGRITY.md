# Git integrity baseline

Captured before repair.

| Repository | `git fsck --full --no-reflogs` | Conflict markers | In-progress operation |
|---|---|---:|---|
| Backend | PASS with unreachable/dangling objects only | 0 | none |
| Frontend | PASS with unreachable/dangling objects only | 0 | none |
| Financial Service | PASS with unreachable/dangling objects only | 0 | none |
| Financial governance | PASS | 0 | none |

Dangling commits and objects are retained by Git and are not corruption. No invalid object, missing object, unresolved index stage, textual conflict marker, or repository lock was found.

The backend branch has no configured upstream. The other three primary checkouts track their corresponding origin feature branches.

## Initial textual versus semantic result

- Textual Git conflicts in checked-out worktrees: `0`
- Unresolved conflict markers: `0`
- Known remote PRs reported as conflicting by GitHub: backend PRs `#2`, `#19`, `#30`; frontend PR `#5`
- Semantic architecture conflicts: present; tracked in `CONFLICT-REGISTER.md`
