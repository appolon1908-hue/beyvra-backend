BEGIN;
CREATE TABLE schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE orders (id uuid PRIMARY KEY, tenant_ref text NOT NULL, quantity numeric(36,18) NOT NULL CHECK (quantity > 0), filled_quantity numeric(36,18) NOT NULL DEFAULT 0 CHECK (filled_quantity >= 0 AND filled_quantity <= quantity), state text NOT NULL, committed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE trades (id uuid PRIMARY KEY, order_id uuid NOT NULL REFERENCES orders(id) ON DELETE RESTRICT, execution_id text NOT NULL UNIQUE, quantity numeric(36,18) NOT NULL CHECK (quantity > 0));
CREATE TABLE settlements (id uuid PRIMARY KEY, trade_id uuid NOT NULL UNIQUE REFERENCES trades(id) ON DELETE RESTRICT, amount numeric(36,18) NOT NULL);
CREATE TABLE reservations (id uuid PRIMARY KEY, order_id uuid NOT NULL UNIQUE REFERENCES orders(id) ON DELETE RESTRICT, original_amount numeric(36,18) NOT NULL, remaining_amount numeric(36,18) NOT NULL CHECK (remaining_amount >= 0), state text NOT NULL);
CREATE TABLE positions (tenant_ref text NOT NULL, instrument_id text NOT NULL, quantity numeric(36,18) NOT NULL, PRIMARY KEY (tenant_ref, instrument_id));
CREATE TABLE simulated_accounts (tenant_ref text PRIMARY KEY, total_balance numeric(36,18) NOT NULL CHECK (total_balance >= 0), pending_balance numeric(36,18) NOT NULL CHECK (pending_balance >= 0 AND pending_balance <= total_balance));
CREATE TABLE outbox_events (event_id uuid PRIMARY KEY, aggregate_id uuid NOT NULL, tenant_ref text NOT NULL, state text NOT NULL DEFAULT 'PENDING');
CREATE TABLE processed_events (event_id uuid NOT NULL, consumer_name text NOT NULL, payload_hash text NOT NULL, PRIMARY KEY (event_id, consumer_name));
CREATE TABLE audit_events (event_id uuid PRIMARY KEY, tenant_ref text NOT NULL, resource_id uuid NOT NULL, action text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE reconciliation_records (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, result text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit events are append-only'; END $$;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
CREATE INDEX orders_tenant_state_idx ON orders (tenant_ref, state);
CREATE INDEX outbox_pending_idx ON outbox_events (state, event_id);

INSERT INTO schema_migrations(name) VALUES ('dr_fixture_v1');
INSERT INTO orders VALUES ('00000000-0000-4000-8000-000000000001','tenant-a',10,10,'FILLED',now()), ('00000000-0000-4000-8000-000000000002','tenant-b',4,0,'OPEN',now());
INSERT INTO trades VALUES ('10000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','exec-1',10);
INSERT INTO settlements VALUES ('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',1000);
INSERT INTO reservations VALUES ('30000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001',1000,0,'CONSUMED'), ('30000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000002',400,400,'ACTIVE');
INSERT INTO positions VALUES ('tenant-a','BTC-USD',10), ('tenant-b','BTC-USD',0);
INSERT INTO simulated_accounts VALUES ('tenant-a',10000,0), ('tenant-b',10000,400);
INSERT INTO outbox_events VALUES ('40000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','tenant-a','PENDING'), ('40000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000002','tenant-b','PENDING');
INSERT INTO processed_events VALUES ('40000000-0000-4000-8000-000000000001','settlement-v1','fixture-hash');
INSERT INTO audit_events VALUES ('50000000-0000-4000-8000-000000000001','tenant-a','00000000-0000-4000-8000-000000000001','ORDER_FILLED',now()), ('50000000-0000-4000-8000-000000000002','tenant-b','00000000-0000-4000-8000-000000000002','ORDER_ACCEPTED',now());
COMMIT;

