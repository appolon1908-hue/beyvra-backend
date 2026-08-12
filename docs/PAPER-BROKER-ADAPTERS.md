# Paper Broker Adapters

The `ExecutionProvider` interface covers capabilities, health, preview, submit, cancel, replace, order lookup/listing, execution listing, and unknown-operation resolution.

`PaperExecutionProvider` requires a `paper-` provider ID, accepts only deterministic fixture prices, and contains no HTTP, socket, credential, account, or production endpoint implementation. Results are labeled `PAPER`. No external paper account was used or certified.
