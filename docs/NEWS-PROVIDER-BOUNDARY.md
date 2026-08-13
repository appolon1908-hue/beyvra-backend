# News-provider boundary

News and calendar never participate in price/trading authority. Canonical news fields are `news_id`, headline, summary, source, publication time, URL, instrument references, provider ID, and receipt time. Calendar fields are event ID, country, currency, title, scheduled time, importance, actual, forecast, previous, and provider ID.

Without verified license and governance approval, news returns HTTP 503 `PROVIDER_NOT_AVAILABLE` and calendar remains `CALENDAR_AVAILABLE=false`. No scraper or fabricated fallback is permitted. Redistribution/display/storage rights must be separately recorded before activation. `NEWS_PROVIDER_ACTIVATED=NO`; `CALENDAR_PROVIDER_ACTIVATED=NO`.

