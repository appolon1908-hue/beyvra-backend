# Sequences and recovery

Gateway events include `event_id`, `version`, `channel`, `sequence`, ISO-8601
`occurred_at`, and `data`. Duplicate or older sequences are ignored by the
frontend. A sequence gap triggers market snapshot recovery before the chart is
trusted again. Durable resume cursors require NATS/Centrifugo history and are
not claimed until deployed.

The supported client model is REST snapshot plus WebSocket deltas. Stateful
views first load the canonical REST snapshot, then subscribe to the matching
realtime channel. If the client observes a gap, such as sequence `101` followed
by `105`, it must mark the local state incomplete, fetch the snapshot provider
declared in the channel registry, and replace the local baseline before
applying later deltas. The current plain `resume` action acknowledges the active
subscriptions only; it is not a durable replay guarantee by itself.
