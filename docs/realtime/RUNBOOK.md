# Realtime runbook checkpoint

On feed failure, keep the last trusted snapshot visible, mark data stale and
disable new demo orders. On gateway failure, use the preserved staging image
and legacy route rollback. Never enable real-money or payment channels as a
recovery action.
