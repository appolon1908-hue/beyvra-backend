# Architecture Branch Topology

Captured from `/root/github-projects/backend` on 2026-08-12. The consolidation
base is `34814195ab86b00ac2f5013bbf9946d732fb6c8e`. Counts are recomputed from the
current local/remote refs and are not copied from prior mission reports.

| Branch | Head | Merge base | Unique commits | Changed files | Classification |
|---|---|---|---:|---:|---|
| `feat/backend-p0-consolidation` | `34814195ab86b00ac2f5013bbf9946d732fb6c8e` | same | 0 | 0 | SOURCE_FOR_INTEGRATION |
| `feat/best-execution-smart-order-routing` | `72c5554a38db33586cfca2a76f00d67eebf3bf20` | consolidation | 30 | 172 | SOURCE_FOR_INTEGRATION |
| `feat/execution-routing-authority` | `5562fd273a0b1a2fc307b1404dd2967f84dc291a` | consolidation | 19 | 126 | PARTIALLY_SUPERSEDED |
| `feat/provider-market-data-readiness` | `8a8847a5eca132b7086313b93978aabc9611713b` | consolidation | 16 | 117 | SOURCE_FOR_INTEGRATION |
| `feat/institutional-account-clearing-authority` | `53f62cc69bc37950c4d338ec60be4daea9adcab1` | consolidation | 21 | 170 | SOURCE_FOR_INTEGRATION |
| `feat/post-trade-settlement-authority` | `97b4cbb2bff83d6860050e450648b6f06f536f54` | consolidation | 25 | 275 | SOURCE_FOR_INTEGRATION |
| `feat/valuation-pnl-performance-authority` | `f65addd660272ed233b244ca66c7cb1a2e3931d2` | consolidation | 27 | 307 | SOURCE_FOR_INTEGRATION |
| `feat/margin-collateral-exposure-authority` | `ec144008d8b754a28dd85ff1fea2fd6fc0c235ab` | consolidation | 23 | 221 | SOURCE_FOR_INTEGRATION |
| `feat/trading-observability-readiness` | `df45c9b71df6dbbb55de9b964193ab90c5af2358` | consolidation | 17 | 116 | SOURCE_FOR_INTEGRATION |
| `feat/disaster-recovery-readiness` | `8534d3abe0657c752bb1cff154c2e4178ccf9b37` | consolidation | 29 | 148 | SOURCE_FOR_INTEGRATION |
| `origin/feat/financial-service-contract-readiness` | `c8636c33fd4a95676c2c9acd1a67aaf461d17c2e` | `3a7e5138380dc96c0e031a3df776d5cda5e1f319` | 10 | 76 | SOURCE_FOR_INTEGRATION |
| `origin/feat/operational-product-control-plane` | `18d877f6d55138965afd7e659754ab110bd628c4` | `5a308d6bdb002ae718d8b62e664f02c6328962b0` | 19 | 104 | SOURCE_FOR_INTEGRATION |
| `origin/feat/canonical-api-realtime-prep` | `a454f444822ab943ec8cbdcead007acb1b77f9e4` | consolidation | 5 | 25 | PARTIALLY_SUPERSEDED |
| `origin/feat/simulated-e2e-trading` | `b07a04fdde91b9c5eb6e3f12a80e212bd30aa305` | consolidation | 10 | 49 | PARTIALLY_SUPERSEDED |
| `origin/feat/simulated-trading-chaos-harness` | `25426b705f8b3f25d08ce63772aa3b1ecb51f240` | consolidation | 11 | 62 | PARTIALLY_SUPERSEDED |
| `origin/feat/polygon-oms-integration-readiness` | `d9fd2faabb5cccfa929c3e2acac8fedb61975ad2` | consolidation | 31 | 165 | NOT_REQUIRED_FOR_CORE_CONVERGENCE |

`feat/beyvra-architecture-convergence` selectively integrates or manually
ports the source branches above. Shared ancestry is integrated once; sibling
tips are not blindly unioned. Provider-native business models and live provider
activation are explicitly outside the core authority graph.
