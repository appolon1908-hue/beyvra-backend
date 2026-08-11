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

Provider activation is not controlled by environment switches. The only
provider-related path setting is:

```text
PROVIDER_CREDENTIAL_ROOT=/etc/codestra/providers
```

The authoritative database approval and license records must reference a file
below this root. The runtime verifies containment, regular-file type, mode
`0600`, and readability before an adapter can run.
