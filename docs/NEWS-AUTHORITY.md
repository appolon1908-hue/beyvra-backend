# News authority

Beyvra owns the public contract at `/api/v1/news*`. NewsData is a replaceable server-side provider and is never browser authority. Canonical filters are `q`, `instrument`, `category`, `source`, `language`, `country`, `published_after`, `published_before`, `limit`, and `cursor`.

Every article records provider identity, provider article ID, receive/provider timestamps, normalizer version and a raw-payload hash without persisting the raw payload. Explicit provider coin/symbol metadata may map instruments; headline substring inference is forbidden. News cannot create orders, bypass risk, or invoke external execution.

External article/image URLs accept HTTPS only. Content is plain text; provider HTML is never rendered as HTML. Browser links must use `noopener noreferrer` and image components must retain fallback behavior.

