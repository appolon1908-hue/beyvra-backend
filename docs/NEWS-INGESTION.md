# News ingestion

The bounded workflow is authorize → fetch → size/schema validate → normalize → deduplicate/upsert transactionally → map explicit instruments → enqueue canonical outbox event → cache canonical response.

Identical `(provider_id, provider_article_id)` and identical payload hash create no second row and no second event. Updates preserve identity and create `news.article.updated`. New articles create `news.article.published`. Polling must be scheduled according to approved quota and delay; no default polling schedule or infinite loop is introduced.

Cache TTLs: Latest 5 minutes, Crypto 10 minutes, Market 10 minutes, Sources 24 hours. Archive is not cached or callable without entitlement. Cached responses retain delayed/stale disclosure.

