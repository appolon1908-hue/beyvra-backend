# Provider credential references

Reserved root-only directories:

```text
/etc/codestra/providers/market/
/etc/codestra/providers/news/
/etc/codestra/providers/calendar/
```

Directories are mode `0700`; provider secret files must be root-owned mode
`0600`. Values are never committed, logged, or exposed to frontend bundles.
No provider credential is currently installed or activated.
