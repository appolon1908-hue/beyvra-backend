# Sequences and recovery

Gateway events include `event_id`, `version`, `channel`, `sequence`, ISO-8601
`occurred_at`, and `data`. Duplicate or older sequences are ignored by the
frontend. A sequence gap triggers market snapshot recovery before the chart is
trusted again. Durable resume cursors require NATS/Centrifugo history and are
not claimed until deployed.
