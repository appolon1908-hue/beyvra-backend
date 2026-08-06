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

The directories were verified on 2026-08-06 as root-owned mode `0700` and
empty. Runtime configuration refers to credentials by protected reference;
secret values must never be placed in approval records or environment files.

Market activation requires all of the following settings and defaults off:

```text
MARKET_PROVIDER_ENABLED=false
MARKET_PROVIDER_APPROVAL_REFERENCE=
MARKET_PROVIDER_LICENSE_REFERENCE=
MARKET_PROVIDER_CREDENTIAL_REFERENCE=
```
