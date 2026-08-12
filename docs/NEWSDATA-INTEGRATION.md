# NewsData integration

Contract checked 2026-08-11 against NewsData's current documentation and endpoint-specific official documentation.

- Base URL: `https://newsdata.io/api/1`
- Authentication: API key as the `apikey` request parameter. The key is loaded server-side from `NEWSDATA_API_KEY`, `NEWSDATA_API_KEY_FILE`, or an approved versioned provider credential file; it is never returned or logged.
- GET endpoints: `/latest`, `/crypto`, `/market`, `/sources`, and `/archive`.
- Pagination: response `nextPage` is submitted as request `page`. Beyvra wraps it in an opaque versioned cursor.
- Common success shape: `status`, `totalResults`, `results`, optional `nextPage`; articles use `article_id`, `title`, `link`, `description`, `content`, `pubDate`, source, language, country/category and optional enrichment fields.
- Errors are provider JSON with error status/message/code and HTTP 4xx/5xx. Beyvra discards provider bodies and emits canonical safe codes.

Current allowed mappings are deliberately narrower than the provider surface: `q`, `language`, `country`, `category`, `source→domain`, date filters for archive, `instrument→coin` for crypto, `instrument→symbol` for market, `limit→size`, and opaque cursor→`page`. Latest covers the preceding 48 hours per current docs. Crypto documents `coin` and requires a paid plan. Market is beta; official documentation says free-plan results are delayed 12 hours and free size is 10 while paid size may reach 50. Sources supports country/category/language. Archive date range depends on paid plan.

No account metadata or credential is present on the host. Entitlements and plan delay are therefore `UNKNOWN`; runtime entitlement flags default false and `NEWSDATA_DELAYED` defaults true. Live calls remain governance-blocked.

