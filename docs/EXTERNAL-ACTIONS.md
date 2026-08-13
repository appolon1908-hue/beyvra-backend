# External action register

Updated 2026-08-11. This register contains only actions that cannot be completed
from the repositories or the authorized staging host.

| Action | Owner required | Blocking condition | Closure evidence |
|---|---|---|---|
| Disposition 12 historical provider credentials (NewsData 2, CoinGecko 5, Polygon 5) | Provider account owners and Platform Security | PR20 cannot merge | Each finding classified as rotated-and-revoked, revoked/no replacement, or evidence-backed false positive; include non-secret provider reference and timestamp |
| Independent security review of PR20 exact head `ee474b09941ff86a2c281901852b1c4ba30a70ee` | Independent security reviewer | PR20 cannot merge | Approval explicitly confirms all 12 disposition records and exact head/base |
| Independent reviews after each base transition | Reviewer other than candidate author | PR6/PR8/PR9 and PR21/PR22 cannot merge | Approval on the final exact head/base after fresh CI |
| Enable enforceable protected-main controls in both private repositories | Repository owner / plan administrator | No protected merge can be certified | GitHub branch protection or ruleset API returns configured required reviews and status checks instead of plan HTTP 403 |

No credential value, replacement credential, or provider secret belongs in this
file. Do not make either repository public merely to obtain branch protection.

