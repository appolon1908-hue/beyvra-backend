# Beyvra isolated chaos harness

This directory is a simulation-only failure/recovery harness. It refuses non-loopback
database URLs and requires `BEYVRA_CHAOS_ISOLATED=1`. Start the disposable stack with:

```sh
./chaos/bin/chaos-harness up
./chaos/bin/chaos-harness certify
./chaos/bin/chaos-harness down
```

`down` is registered as an exit trap by `certify`, so cleanup runs on success, test
failure, and interruption. No host database port is published.
