"""Contract tests for the target transport; runtime certification belongs to B17."""

from pathlib import Path
import unittest

from jsonschema import Draft7Validator, FormatChecker
from rfc3339_validator import validate_rfc3339
import yaml

from validate_openapi import UniqueKeyLoader


ROOT = Path(__file__).resolve().parents[1]


class RealtimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.load(
            (ROOT / "contracts/asyncapi/beyvra-asyncapi-3.0.yaml").read_text(),
            Loader=UniqueKeyLoader,
        )

    def validator(self, event):
        return Draft7Validator(
            {
                "$ref": f"#/components/schemas/{event}",
                "components": self.document["components"],
            },
            format_checker=FormatChecker(),
        )

    def test_all_payload_schemas_are_valid(self):
        for name, schema in self.document["components"]["schemas"].items():
            with self.subTest(schema=name):
                Draft7Validator.check_schema(schema)

    def test_contract_keeps_single_transport_and_records_provenance(self):
        self.assertEqual(self.document["asyncapi"], "3.0.0")
        self.assertFalse(
            self.document["x-beyvra-provenance"]["original_file_available"]
        )
        self.assertEqual(len(self.document["servers"]), 1)
        server = next(iter(self.document["servers"].values()))
        self.assertEqual(server["pathname"], "/ws/v2")
        self.assertEqual(server["protocol"], "wss")

    def envelope(self, data):
        return {
            "event_id": "event-1",
            "event_type": "market.quote.updated.v1",
            "schema_version": 1,
            "correlation_id": "correlation-1",
            "stream_id": "stream-1",
            "sequence": 1,
            "occurred_at": "2026-09-12T00:00:00Z",
            "data": data,
        }

    def test_exactly_the_thirteen_requested_channel_families(self):
        addresses = {
            channel["address"] for channel in self.document["channels"].values()
        }
        self.assertEqual(
            addresses,
            {
                "quotes.{instrumentId}",
                "candles.{instrumentId}.{interval}",
                "accounts.{accountId}.orders",
                "accounts.{accountId}.executions",
                "accounts.{accountId}.positions",
                "accounts.{accountId}.balances",
                "accounts.{accountId}.funding",
                "accounts.{accountId}.crypto",
                "accounts.{accountId}.risk",
                "customers.{customerId}.notifications",
                "system.status",
                "admin.approvals",
                "admin.incidents",
            },
        )
        self.assertEqual(len(self.document["operations"]), 13)
        self.assertTrue(
            all(op["action"] == "send" for op in self.document["operations"].values())
        )

    def test_private_scopes_declare_authorization_and_resynchronization(self):
        for channel in self.document["channels"].values():
            address = channel["address"]
            with self.subTest(address=address):
                policy = channel["x-beyvra-authorization"]
                if address.startswith("accounts."):
                    self.assertEqual(policy, "ACCOUNT_OWNER")
                elif address.startswith("customers."):
                    self.assertEqual(policy, "CUSTOMER_SELF")
                elif address.startswith("admin."):
                    self.assertTrue(policy.startswith("WORKFORCE_"))
                self.assertIn("x-beyvra-snapshot", channel)

    def test_quote_requires_real_price_data_and_decimal_strings(self):
        data = {
            "instrument_id": "instrument-1",
            "quoted_at": "2026-09-12T00:00:00Z",
            "stale": False,
            "last": "100.25",
        }
        event = self.envelope(data)
        validator = self.validator("QuoteEvent")
        self.assertTrue(validator.is_valid(event))
        data["last"] = 100.25
        self.assertFalse(validator.is_valid(event))
        del data["last"]
        self.assertFalse(validator.is_valid(event))

    def test_public_market_events_cannot_include_private_account_scope(self):
        event = self.envelope(
            {
                "instrument_id": "instrument-1",
                "quoted_at": "2026-09-12T00:00:00Z",
                "stale": True,
                "last": "100.25",
            }
        )
        event["account_id"] = "private-account"
        self.assertFalse(self.validator("QuoteEvent").is_valid(event))

    def test_sequences_are_required_positive_and_browser_safe(self):
        event = self.envelope(
            {
                "domain": "market_data",
                "status": "AVAILABLE",
                "as_of": "2026-09-12T00:00:00Z",
            }
        )
        validator = self.validator("SystemStatusEvent")
        self.assertTrue(validator.is_valid(event))
        for value in (0, -1, "1", 9007199254740992):
            with self.subTest(value=value):
                event["sequence"] = value
                self.assertFalse(validator.is_valid(event))
        event.pop("sequence")
        self.assertFalse(validator.is_valid(event))

    def test_candles_do_not_require_fabricated_volume(self):
        event = self.envelope(
            {
                "instrument_id": "instrument-1",
                "interval": "1m",
                "opened_at": "2026-09-12T00:00:00Z",
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.50",
                "closed": True,
            }
        )
        self.assertTrue(self.validator("CandleEvent").is_valid(event))
        event["data"]["interval"] = "unsupported"
        self.assertFalse(self.validator("CandleEvent").is_valid(event))

    def test_account_events_require_private_scope_and_typed_payload(self):
        schemas = self.document["components"]["schemas"]
        for name in (
            "Order",
            "Execution",
            "Position",
            "Balance",
            "Funding",
            "Crypto",
            "Risk",
        ):
            with self.subTest(event=name):
                data = {}
                for field in schemas[name]["required"]:
                    schema = schemas[name]["properties"][field]
                    if schema.get("format") == "date-time":
                        value = "2026-09-12T00:00:00Z"
                    elif "enum" in schema:
                        value = schema["enum"][0]
                    elif "pattern" in schema:
                        value = "1.25"
                    elif schema["type"] == "boolean":
                        value = False
                    else:
                        value = "account-1" if field == "account_id" else "id-1"
                    data[field] = value
                event = self.envelope(data)
                event["account_id"] = "account-1"
                validator = self.validator(f"{name}Event")
                self.assertTrue(validator.is_valid(event))
                del event["account_id"]
                self.assertFalse(validator.is_valid(event))
                event["account_id"] = "account-1"
                event["customer_id"] = "unrelated-customer"
                self.assertFalse(validator.is_valid(event))
                del event["customer_id"]
                del data["account_id"]
                self.assertFalse(validator.is_valid(event))

    def test_event_timestamps_reject_invalid_dates(self):
        self.assertFalse(validate_rfc3339("2026-02-30T00:00:00Z"))
        event = self.envelope(
            {
                "domain": "market_data",
                "status": "AVAILABLE",
                "as_of": "2026-09-12T00:00:00Z",
            }
        )
        validator = self.validator("SystemStatusEvent")
        event["occurred_at"] = "not-a-timestamp"
        self.assertFalse(validator.is_valid(event))
        event["occurred_at"] = "2026-09-12T00:00:00Z"
        event["data"]["as_of"] = "2026-02-30T00:00:00Z"
        self.assertFalse(validator.is_valid(event))


if __name__ == "__main__":
    unittest.main()
