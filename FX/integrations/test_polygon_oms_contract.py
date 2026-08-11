import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from integrations.financial.polygon_oms_contract import (
    AssetNetwork,
    CircuitBreaker,
    CircuitState,
    CanonicalKycState,
    CanonicalProviderError,
    CanonicalTransactionState,
    EntityMapping,
    FixtureInbox,
    OutboundGate,
    Quote,
    WalletMapping,
    canonical_kyc_state,
    canonical_transaction_state,
    decimal_string,
    map_provider_error,
    resolve_unknown_outcome,
    retry_delay,
    require_tenant_owner,
    verify_webhook_signature,
    validate_transaction_response,
)


FIXTURES = Path(__file__).parent / "fixtures" / "polygon_oms_contracts.json"


class PolygonOmsContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))

    def test_fixture_inventory_is_complete_and_synthetic(self):
        expected = {"entity", "wallet", "quote", "transaction", "onramp", "offramp", "transfer", "compliance", "webhook"}
        self.assertEqual(set(self.fixtures), expected)
        self.assertNotIn("@", json.dumps(self.fixtures))

    def test_money_is_decimal_and_float_is_rejected(self):
        self.assertEqual(decimal_string("100.01"), Decimal("100.01"))
        for invalid in (1.2, True, None, "NaN", "Infinity"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                decimal_string(invalid)

    def test_asset_network_requires_explicit_identity_and_precision(self):
        value = AssetNetwork("usdc", "polygon", "polygon", 6)
        self.assertEqual(value.decimals, 6)
        with self.assertRaises(ValueError):
            AssetNetwork("usdc", "", "", 6)

    def test_entity_and_wallet_mappings_keep_beyvra_identity(self):
        entity = EntityMapping("tenant_fixture_a", "acct_fixture_a", "cst_fixture_a")
        wallet = WalletMapping("tenant_fixture_a", "wallet_fixture_a", "wlt_fixture_a", "usdc", "polygon", "UNDECIDED", "PENDING")
        self.assertNotEqual(entity.beyvra_account_ref, entity.oms_entity_ref)
        self.assertNotEqual(wallet.wallet_ref, wallet.provider_wallet_ref)

    def test_cross_tenant_oms_mapping_access_is_hidden(self):
        require_tenant_owner("tenant_fixture_a", "tenant_fixture_a")
        with self.assertRaisesRegex(PermissionError, "RESOURCE_NOT_FOUND"):
            require_tenant_owner("tenant_fixture_b", "tenant_fixture_a")

    def test_quote_has_no_execution_side_effect(self):
        quote = Quote.from_fixture(self.fixtures["quote"])
        self.assertEqual(quote.input_amount, Decimal("100.00"))
        self.assertEqual(quote.fee, Decimal("1.00"))

    def test_documented_transaction_states_map(self):
        self.assertEqual(canonical_transaction_state("processing"), CanonicalTransactionState.PROCESSING)
        self.assertEqual(canonical_transaction_state("awaitingAction"), CanonicalTransactionState.REQUIRES_ACTION)
        self.assertEqual(canonical_transaction_state("completed"), CanonicalTransactionState.SETTLED)

    def test_unknown_transaction_state_fails_closed(self):
        self.assertEqual(canonical_transaction_state("futureState"), CanonicalTransactionState.UNKNOWN)

    def test_unknown_kyc_state_never_approves(self):
        self.assertEqual(canonical_kyc_state("approved"), CanonicalKycState.APPROVED)
        self.assertEqual(canonical_kyc_state("futureState"), CanonicalKycState.IN_REVIEW)

    def test_provider_errors_map_to_bounded_canonical_codes(self):
        cases = (
            (400, {}, CanonicalProviderError.VALIDATION_ERROR),
            (401, {}, CanonicalProviderError.OPERATION_NOT_ALLOWED),
            (403, {}, CanonicalProviderError.OPERATION_NOT_ALLOWED),
            (409, {}, CanonicalProviderError.IDEMPOTENCY_CONFLICT),
            (422, {"code": "compliance_hold"}, CanonicalProviderError.COMPLIANCE_REQUIRED),
            (422, {"code": "insufficient_funds"}, CanonicalProviderError.INSUFFICIENT_FUNDS),
            (429, {}, CanonicalProviderError.PROVIDER_UNAVAILABLE),
            (500, {}, CanonicalProviderError.PROVIDER_UNAVAILABLE),
            (418, "raw provider detail", CanonicalProviderError.UNKNOWN_OUTCOME),
        )
        for status, body, expected in cases:
            with self.subTest(status=status, expected=expected):
                self.assertEqual(map_provider_error(status, body), expected)

    def test_transaction_response_validation_rejects_malformed_and_float(self):
        self.assertEqual(
            validate_transaction_response({"id": "txn_fixture", "status": "processing", "amount": "1.25"}),
            ("txn_fixture", CanonicalTransactionState.PROCESSING, Decimal("1.25")),
        )
        for malformed in (None, {}, {"id": "txn", "status": "processing", "amount": 1.25}):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                validate_transaction_response(malformed)

    def test_default_outbound_gate_denies_before_network(self):
        gate = OutboundGate()
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.reason(), "GLOBAL_FINANCIAL_HALT")

    def test_global_halt_precedes_all_approvals(self):
        gate = OutboundGate(
            polygon_oms_enabled=True,
            polygon_oms_halted=False,
            all_financial_mutations_halted=True,
            environment_approved=True,
            credential_available=True,
            operation_approved=True,
            compliance_approved=True,
            financial_approved=True,
            feature_enabled=True,
        )
        self.assertEqual(gate.reason(), "GLOBAL_FINANCIAL_HALT")

    def test_kill_switch_precedes_provider_enablement(self):
        gate = OutboundGate(polygon_oms_enabled=True, all_financial_mutations_halted=False)
        self.assertEqual(gate.reason(), "POLYGON_OMS_HALTED")

    def test_every_gate_is_required(self):
        allowed = dict(
            polygon_oms_enabled=True,
            polygon_oms_halted=False,
            all_financial_mutations_halted=False,
            environment_approved=True,
            credential_available=True,
            operation_approved=True,
            compliance_approved=True,
            financial_approved=True,
            feature_enabled=True,
        )
        self.assertTrue(OutboundGate(**allowed).allowed)
        for key in allowed:
            denied = dict(allowed)
            denied[key] = not denied[key]
            with self.subTest(key=key):
                self.assertFalse(OutboundGate(**denied).allowed)

    def test_production_requires_separate_enablement(self):
        gate = OutboundGate(
            polygon_oms_enabled=True,
            polygon_oms_halted=False,
            all_financial_mutations_halted=False,
            environment_approved=True,
            credential_available=True,
            operation_approved=True,
            compliance_approved=True,
            financial_approved=True,
            feature_enabled=True,
            production_requested=True,
        )
        self.assertEqual(gate.reason(), "PRODUCTION_NOT_APPROVED")

    def test_circuit_breaker_opens_and_recovers_through_half_open(self):
        circuit = CircuitBreaker(failure_threshold=2)
        self.assertEqual(circuit.record_failure(), CircuitState.CLOSED)
        self.assertEqual(circuit.record_failure(), CircuitState.OPEN)
        self.assertTrue(circuit.begin_probe())
        self.assertEqual(circuit.record_success(), CircuitState.CLOSED)

    def _signed(self, body, now=1_800_000_000, key=b"fixture-signing-key"):
        signature = hmac.new(key, str(now).encode() + b"." + body, hashlib.sha256).hexdigest()
        return f"t={now},v1={signature}"

    def test_valid_webhook_signature(self):
        body = json.dumps(self.fixtures["webhook"], separators=(",", ":")).encode()
        self.assertTrue(verify_webhook_signature(body, self._signed(body), b"fixture-signing-key", now=1_800_000_000))

    def test_invalid_missing_and_malformed_signatures(self):
        body = b"{}"
        for header in (None, "", "t=x,v1=no", "t=1800000000,v1=00"):
            with self.subTest(header=header):
                self.assertFalse(verify_webhook_signature(body, header, b"fixture-signing-key", now=1_800_000_000))

    def test_webhook_timestamp_replay_window(self):
        body = b"{}"
        header = self._signed(body, now=1_799_999_699)
        self.assertFalse(verify_webhook_signature(body, header, b"fixture-signing-key", now=1_800_000_000))

    def test_raw_body_integrity_is_signed(self):
        compact = b'{"id":"whd_fixture"}'
        pretty = b'{ "id": "whd_fixture" }'
        self.assertFalse(verify_webhook_signature(pretty, self._signed(compact), b"fixture-signing-key", now=1_800_000_000))

    def test_same_webhook_100_times_has_one_business_effect(self):
        inbox = FixtureInbox()
        body = json.dumps(self.fixtures["webhook"]).encode()
        results = [inbox.apply(body) for _ in range(100)]
        self.assertEqual(results.count("APPLIED"), 1)
        self.assertEqual(inbox.business_effects, 1)

    def test_unknown_event_dead_letters_without_mutation(self):
        event = dict(self.fixtures["webhook"], id="whd_unknown", eventType="future.event")
        inbox = FixtureInbox()
        self.assertEqual(inbox.apply(json.dumps(event).encode()), "UNKNOWN_EVENT")
        self.assertEqual(inbox.business_effects, 0)

    def test_malformed_webhook_has_no_mutation(self):
        inbox = FixtureInbox()
        self.assertEqual(inbox.apply(b"{"), "MALFORMED")
        self.assertEqual(inbox.business_effects, 0)

    def test_out_of_order_event_is_ignored(self):
        inbox = FixtureInbox()
        first = dict(self.fixtures["webhook"], id="whd_first", sequence=1)
        newer = dict(self.fixtures["webhook"], id="whd_new", sequence=2)
        older = dict(self.fixtures["webhook"], id="whd_old", sequence=1)
        self.assertEqual(inbox.apply(json.dumps(first).encode()), "APPLIED")
        self.assertEqual(inbox.apply(json.dumps(newer).encode()), "APPLIED")
        self.assertEqual(inbox.apply(json.dumps(older).encode()), "STALE")
        self.assertEqual(inbox.business_effects, 2)

    def test_sequence_gap_requires_reconciliation(self):
        inbox = FixtureInbox()
        first = dict(self.fixtures["webhook"], id="whd_first", sequence=1)
        gap = dict(self.fixtures["webhook"], id="whd_gap", sequence=3)
        self.assertEqual(inbox.apply(json.dumps(first).encode()), "APPLIED")
        self.assertEqual(inbox.apply(json.dumps(gap).encode()), "SEQUENCE_GAP")
        self.assertEqual(inbox.business_effects, 1)

    def test_terminal_state_does_not_regress(self):
        inbox = FixtureInbox()
        completed = dict(self.fixtures["webhook"], id="whd_done", sequence=1)
        pending = json.loads(json.dumps(completed))
        pending.update(id="whd_late", sequence=2)
        pending["data"]["status"] = "processing"
        self.assertEqual(inbox.apply(json.dumps(completed).encode()), "APPLIED")
        self.assertEqual(inbox.apply(json.dumps(pending).encode()), "INVALID_TRANSITION")

    def test_unknown_state_dead_letters(self):
        inbox = FixtureInbox()
        event = json.loads(json.dumps(self.fixtures["webhook"]))
        event["id"] = "whd_future"
        event["data"]["status"] = "futureState"
        self.assertEqual(inbox.apply(json.dumps(event).encode()), "UNKNOWN_STATE")

    def test_unknown_outcome_looks_up_before_create(self):
        calls = {"create": 0}
        existing = {"id": "txn_existing", "status": "processing"}
        result = resolve_unknown_outcome("operation-a", lambda _ref: existing, lambda: calls.__setitem__("create", 1))
        self.assertEqual(result, existing)
        self.assertEqual(calls["create"], 0)

    def test_100_duplicate_operations_create_one_logical_operation(self):
        operations = {}
        creates = 0

        def create():
            nonlocal creates
            creates += 1
            value = {"id": "txn_fixture"}
            operations["stable-key"] = value
            return value

        for _ in range(100):
            resolve_unknown_outcome("stable-key", operations.get, create)
        self.assertEqual(creates, 1)

    def test_retry_policy_is_bounded_and_honors_retry_after(self):
        self.assertEqual(retry_delay(429, "7", 0), 7.0)
        self.assertEqual(retry_delay(503, None, 3), 8.0)
        self.assertIsNone(retry_delay(400, None, 0))
        self.assertIsNone(retry_delay(503, None, 5))

    def test_fixture_load_profiles_do_not_call_network(self):
        values = []
        for count in (100, 1000, 5000):
            start = time.perf_counter()
            for _ in range(count):
                Quote.from_fixture(self.fixtures["quote"])
                canonical_transaction_state("processing")
            values.append(time.perf_counter() - start)
        self.assertEqual(len(values), 3)
