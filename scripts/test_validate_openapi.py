"""Regressions for invalid contracts that previously passed the YAML-only gate."""

import unittest

import yaml

from validate_openapi import UniqueKeyLoader, canonical_specs, validate_document


def contract():
    return {
        "openapi": "3.1.0",
        "paths": {"/api/v1/accounts": {"get": {"operationId": "listAccounts"}}},
        "components": {"schemas": {"Account": {"type": "object"}}},
    }


class OpenApiValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
