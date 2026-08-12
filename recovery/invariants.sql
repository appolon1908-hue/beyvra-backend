\set ON_ERROR_STOP on
DO $$
DECLARE failures integer;
BEGIN
  SELECT count(*) INTO failures FROM orders o LEFT JOIN outbox_events e ON e.aggregate_id=o.id WHERE e.event_id IS NULL;
  IF failures <> 0 THEN RAISE EXCEPTION 'LOST_COMMITTED_OUTBOX_EVENTS=%', failures; END IF;
  SELECT count(*)-count(DISTINCT execution_id) INTO failures FROM trades;
  IF failures <> 0 THEN RAISE EXCEPTION 'DUPLICATE_TRADES=%', failures; END IF;
  SELECT count(*)-count(DISTINCT trade_id) INTO failures FROM settlements;
  IF failures <> 0 THEN RAISE EXCEPTION 'DUPLICATE_SETTLEMENTS=%', failures; END IF;
  SELECT count(*) INTO failures FROM reservations r JOIN orders o ON o.id=r.order_id WHERE o.state IN ('FILLED','CANCELLED','REJECTED','EXPIRED') AND r.state='ACTIVE';
  IF failures <> 0 THEN RAISE EXCEPTION 'RESERVATION_LEAKS=%', failures; END IF;
  SELECT count(*) INTO failures FROM orders WHERE filled_quantity < 0 OR filled_quantity > quantity;
  IF failures <> 0 THEN RAISE EXCEPTION 'POSITION_ACCOUNTING_ERRORS=%', failures; END IF;
  SELECT count(*) INTO failures FROM orders o LEFT JOIN audit_events a ON a.resource_id=o.id AND a.tenant_ref=o.tenant_ref WHERE a.event_id IS NULL;
  IF failures <> 0 THEN RAISE EXCEPTION 'AUDIT_HISTORY_LOST=%', failures; END IF;
END $$;
INSERT INTO reconciliation_records(result) VALUES ('PASS');

