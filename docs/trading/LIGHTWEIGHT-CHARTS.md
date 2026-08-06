# Lightweight Charts

The frontend primary chart module is under
`src/features/trading-chart/` and pins Lightweight Charts 5.0.5. It owns chart
mount/unmount, candle and volume series, overlays, markers, theme, resize, and
realtime subscription cleanup. Demo overlays are visual only and call approved
demo APIs for actions; the chart never mutates financial state locally.
