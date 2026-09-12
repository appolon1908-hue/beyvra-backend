"""Regressions for invalid contracts that previously passed the YAML-only gate."""

import unittest

import yaml

from validate_openapi import (
    PINNED_FINANCIAL_SPEC,
    UniqueKeyLoader,
    canonical_specs,
    validate_document,
    validate_file,
)


def contract():
    return {
        "openapi": "3.1.0",
        "paths": {"/api/v1/accounts": {"get": {"operationId": "listAccounts"}}},
        "components": {"schemas": {"Account": {"type": "object"}}},
    }


class OpenApiValidationTests(unittest.TestCase):
    def test_pinned_dependency_keeps_upstream_identity_and_validation(self):
        self.assertNotIn(PINNED_FINANCIAL_SPEC, canonical_specs())
        validate_file(PINNED_FINANCIAL_SPEC)

    def test_checked_in_documents(self):
        self.assertTrue(canonical_specs())
        for path in canonical_specs():
            with self.subTest(path=path):
                validate_document(yaml.load(path.read_text(), Loader=UniqueKeyLoader))

    def test_duplicate_yaml_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
            yaml.load("paths: {}\npaths: {}\n", Loader=UniqueKeyLoader)

    def test_operation_ids_are_unique_across_paths_and_methods(self):
        document = contract()
        document["paths"]["/api/v1/orders"] = {"post": {"operationId": "listAccounts"}}
        with self.assertRaisesRegex(ValueError, "duplicate operationId"):
            validate_document(document)

    def test_nested_missing_reference_is_rejected(self):
        document = contract()
        document["components"]["schemas"]["Account"] = {
            "allOf": [{"$ref": "#/components/schemas/Absent"}]
        }
        with self.assertRaisesRegex(ValueError, "unresolved local"):
            validate_document(document)

    def test_recursive_schema_is_valid_without_following_cycles(self):
        document = contract()
        document["components"]["schemas"]["Account"]["properties"] = {
            "parent": {"$ref": "#/components/schemas/Account"}
        }
        validate_document(document)

    def test_escaped_pointer_and_array_reference(self):
        document = contract()
        document["components"]["schemas"]["a/b~c"] = {"allOf": [{"type": "string"}]}
        document["components"]["schemas"]["Alias"] = {
            "$ref": "#/components/schemas/a~1b~0c/allOf/0"
        }
        validate_document(document)

    def test_external_reference_is_not_silently_accepted(self):
        document = contract()
        document["components"]["schemas"]["Alias"] = {"$ref": "other.yaml#/Account"}
        with self.assertRaisesRegex(ValueError, "external"):
            validate_document(document)

    def test_invalid_shapes_are_rejected(self):
        for value in (None, [], {}, {"openapi": "3.1.0", "paths": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_document(value)

    def test_invalid_operation_identity_is_rejected(self):
        for value in ([], {}, "", 123):
            document = contract()
            document["paths"]["/api/v1/accounts"]["get"]["operationId"] = value
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "invalid operationId"),
            ):
                validate_document(document)

    def test_missing_operation_id_is_rejected(self):
        document = contract()
        document["paths"]["/api/v1/accounts"]["get"].pop("operationId")
        with self.assertRaisesRegex(ValueError, "missing operationId"):
            validate_document(document)

    def test_retired_operation_id_cannot_hide_under_canonical_path(self):
        document = contract()
        document["paths"]["/api/v1/accounts"]["get"]["operationId"] = "getDemoWallet"
        with self.assertRaisesRegex(ValueError, "retired Demo operationId"):
            validate_document(document)

    def test_retired_and_provider_specific_customer_paths_are_rejected(self):
        for path in (
            "/api/v1/demo",
            "/api/v1/demo/orders",
            "/api/admin/v1/accounts/{accountId}/demo-credit",
            "/api/admin/v1/accounts/{accountId}/demo-reset/",
            "/api/v1/polygon/quotes",
            "/api/v1/funding/stripe/deposits",
        ):
            document = contract()
            document["paths"][path] = {"post": {"operationId": "forbiddenCommand"}}
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_document(document)

    def test_demo_tag_cannot_be_reintroduced(self):
        document = contract()
        document["tags"] = [{"name": "Demo"}]
        with self.assertRaisesRegex(ValueError, "Demo tag"):
            validate_document(document)
        document.pop("tags")
        document["paths"]["/api/v1/accounts"]["get"]["tags"] = ["Demo"]
        with self.assertRaisesRegex(ValueError, "Demo tag"):
            validate_document(document)

    def test_wallet_balance_reads_are_allowed_but_mutations_are_rejected(self):
        document = contract()
        document["paths"]["/api/v1/wallet/USD/balance"] = {
            "get": {"operationId": "readBalance"}
        }
        validate_document(document)
        document["paths"]["/api/v1/wallet/USD/balance"]["patch"] = {
            "operationId": "editBalance"
        }
        with self.assertRaisesRegex(ValueError, "direct financial"):
            validate_document(document)


if __name__ == "__main__":
    unittest.main()
