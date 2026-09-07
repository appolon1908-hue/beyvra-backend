"""Exercise the actual checked-in contracts and adversarial mutations offline."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_beyvra_fabric as validator


class FabricBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.documents = {
            path: validator.load_json(path)
            for path in (validator.FABRIC_PATH, validator.N8N_MANIFEST_PATH, validator.OPENAPI_PATH)
        }

    def validate(self, documents):
        with patch.object(validator, "load_json", side_effect=lambda path: documents[path]):
            validator.main()

    def test_actual_checked_in_contracts_pass(self):
        self.validate(self.documents)

    def test_caller_tenant_authority_cannot_be_enabled_or_omitted(self):
        for value in (True, None, "false", 0):
            with self.subTest(value=value):
                docs = copy.deepcopy(self.documents)
                docs[validator.N8N_MANIFEST_PATH]["invariants"]["caller_tenant_authoritative"] = value
                with self.assertRaisesRegex(SystemExit, "caller_tenant_authoritative"):
                    self.validate(docs)
        docs = copy.deepcopy(self.documents)
        del docs[validator.N8N_MANIFEST_PATH]["invariants"]["caller_tenant_authoritative"]
        with self.assertRaisesRegex(SystemExit, "caller_tenant_authoritative"):
            self.validate(docs)

    def test_event_allowlist_rejects_expansion_omission_duplicates_and_bad_types(self):
        events = self.documents[validator.N8N_MANIFEST_PATH]["allowed_events"]
        for changed in (events + ["beyvra.trade.executed"], events[:-1], events + events[:1], None, [{}]):
            with self.subTest(events=changed):
                docs = copy.deepcopy(self.documents)
                docs[validator.N8N_MANIFEST_PATH]["allowed_events"] = changed
                with self.assertRaisesRegex(SystemExit, "allowed_events"):
                    self.validate(docs)

    def test_missing_header_definitions_do_not_pass_on_literal_refs(self):
        for key in validator.EXPECTED_HEADERS:
            with self.subTest(key=key):
                docs = copy.deepcopy(self.documents)
                del docs[validator.OPENAPI_PATH]["components"]["parameters"][key]
                with self.assertRaisesRegex(SystemExit, "command header definition"):
                    self.validate(docs)

    def test_header_semantics_and_schema_cannot_be_weakened(self):
        for field, value in (("required", False), ("in", "query"), ("name", "Unused-Key"),
                             ("schema", {"type": "integer"}), ("schema", {"$ref": "#/missing"})):
            with self.subTest(field=field):
                docs = copy.deepcopy(self.documents)
                docs[validator.OPENAPI_PATH]["components"]["parameters"]["IdempotencyKey"][field] = value
                with self.assertRaisesRegex(SystemExit, "command header definition"):
                    self.validate(docs)

    def test_operation_level_server_overrides_are_rejected_on_all_methods(self):
        for path, methods in validator.EXPECTED_OPENAPI.items():
            for method in methods:
                with self.subTest(path=path, method=method):
                    docs = copy.deepcopy(self.documents)
                    docs[validator.OPENAPI_PATH]["paths"][path][method]["servers"] = [{"url": "https://example.com"}]
                    with self.assertRaisesRegex(SystemExit, "operation-level server override"):
                        self.validate(docs)

    def test_path_level_server_override_is_rejected(self):
        docs = copy.deepcopy(self.documents)
        docs[validator.OPENAPI_PATH]["paths"]["/v1/automation/notifications"]["servers"] = [{"url": "https://example.com"}]
        with self.assertRaisesRegex(SystemExit, "path overrides"):
            self.validate(docs)

    def test_unresolved_external_and_overridden_parameter_refs_are_rejected(self):
        for parameter in ({"$ref": "#/components/parameters/Missing"},
                          {"$ref": "https://example.com/parameter.json"},
                          {"$ref": "#/components/parameters/IdempotencyKey", "required": False}):
            with self.subTest(parameter=parameter):
                docs = copy.deepcopy(self.documents)
                docs[validator.OPENAPI_PATH]["paths"]["/v1/automation/notifications"]["post"]["parameters"][0] = parameter
                with self.assertRaises(SystemExit):
                    self.validate(docs)

    def test_inline_duplicate_header_cannot_override_required_reference(self):
        docs = copy.deepcopy(self.documents)
        docs[validator.OPENAPI_PATH]["paths"]["/v1/automation/notifications"]["post"]["parameters"].append(
            {"name": "idempotency-key", "in": "header", "required": False, "schema": {"type": "string"}}
        )
        with self.assertRaisesRegex(SystemExit, "inline command header override"):
            self.validate(docs)

    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"invariants":{"caller_tenant_authoritative":true,"caller_tenant_authoritative":false}}')
            with self.assertRaisesRegex(SystemExit, "duplicate JSON key"):
                validator.load_json(path)


if __name__ == "__main__":
    unittest.main()
