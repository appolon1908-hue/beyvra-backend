"""Regression tests for false completeness and stale implementation evidence."""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import yaml

from generate_api_implementation_matrix import (
    endpoint_paths,
    inventory,
    render,
    verify_evidence,
)


class ImplementationMatrixTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.document = {
            "openapi": "3.1.0",
            "servers": [{"url": "/api/v1"}],
            "paths": {"/accounts": {"get": {"operationId": "listAccounts"}}},
        }

    def write(self, name, document):
        path = self.root / name
        path.write_text(yaml.safe_dump(document))
        return path

    def rows(self):
        return inventory([self.write("api.yaml", self.document)], root=self.root)[0]

    def evidence(self, status="IMPLEMENTED"):
        source = self.root / "accounts.py"
        source.write_text("# fixture source\n")
        return {
            "listAccounts": {
                "method": "GET",
                "path": "/api/v1/accounts",
                "backend_module": "accounts.py::AccountsView",
                "service": "accounts.py::list_accounts",
                "authorization": "CUSTOMER_OWNER",
                "feature_gate": "NONE",
                "test_file": "accounts.py::test_account_scope",
                "frontend_caller": "NONE: service-only operation",
                "implementation_status": status,
                "file_sha256": {
                    "accounts.py": {
                        "sha256": hashlib.sha256(source.read_bytes()).hexdigest()
                    }
                },
            }
        }

    def test_duplicate_snapshots_share_one_resolved_operation(self):
        absolute = copy.deepcopy(self.document)
        absolute.pop("servers")
        absolute["paths"] = {"/api/v1/accounts": absolute["paths"]["/accounts"]}
        rows, gaps = inventory(
            [
                self.write("relative.yaml", self.document),
                self.write("absolute.yaml", absolute),
            ],
            root=self.root,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows["listAccounts"]["path"], "/api/v1/accounts")
        self.assertEqual(
            rows["listAccounts"]["sources"], {"relative.yaml", "absolute.yaml"}
        )
        self.assertEqual(gaps, [])

    def test_conflicting_operation_id_fails(self):
        other = copy.deepcopy(self.document)
        other["paths"] = {"/orders": other["paths"]["/accounts"]}
        with self.assertRaisesRegex(ValueError, "conflicting operationId"):
            inventory(
                [self.write("one.yaml", self.document), self.write("two.yaml", other)],
                root=self.root,
            )

    def test_missing_ids_are_visible_and_never_silently_dropped(self):
        self.document["paths"]["/accounts"]["post"] = {
            "responses": {"201": {"description": "Created"}}
        }
        rows, gaps = inventory([self.write("api.yaml", self.document)], root=self.root)
        self.assertEqual(len(gaps), 1)
        report = render(rows, gaps)
        self.assertIn("Missing implementation evidence: **1**", report)
        self.assertIn("POST /api/v1/accounts", report)
        self.assertNotIn("implementation_status", rows["listAccounts"])

    def test_operation_server_override_and_default_variables(self):
        operation = {
            "servers": [
                {
                    "url": "https://api.example.invalid/{version}",
                    "variables": {"version": {"default": "v2"}},
                }
            ]
        }
        self.assertEqual(
            endpoint_paths(self.document, {}, operation, "/accounts"), ["/v2/accounts"]
        )
        operation["servers"][0].pop("variables")
        with self.assertRaisesRegex(ValueError, "unresolved server"):
            endpoint_paths(self.document, {}, operation, "/accounts")

    def test_only_valid_source_bound_evidence_assigns_a_status(self):
        rows = self.rows()
        verify_evidence(rows, self.evidence(), root=self.root)
        self.assertEqual(rows["listAccounts"]["implementation_status"], "IMPLEMENTED")

    def test_route_rename_invalidates_evidence(self):
        evidence = self.evidence()
        evidence["listAccounts"]["path"] = "/api/v1/old-accounts"
        with self.assertRaisesRegex(ValueError, "endpoint changed"):
            verify_evidence(self.rows(), evidence, root=self.root)

    def test_source_change_invalidates_evidence(self):
        evidence = self.evidence()
        (self.root / "accounts.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "stale source evidence"):
            verify_evidence(self.rows(), evidence, root=self.root)

    def test_unknown_and_invalid_status_claims_fail(self):
        evidence = self.evidence("NOT_IMPLEMENTED")
        with self.assertRaisesRegex(ValueError, "invalid implementation status"):
            verify_evidence(self.rows(), evidence, root=self.root)
        evidence["unknown"] = evidence.pop("listAccounts")
        with self.assertRaisesRegex(ValueError, "unknown operations"):
            verify_evidence(self.rows(), evidence, root=self.root)

    def test_feature_disabled_alone_is_not_an_implemented_adapter(self):
        evidence = self.evidence("IMPLEMENTED_GATED")
        with self.assertRaisesRegex(ValueError, "requires adapter evidence"):
            verify_evidence(self.rows(), evidence, root=self.root)
        evidence["listAccounts"].update(
            feature_gate="ACCOUNTS_ENABLED", adapter_test="missing.py::test_adapter"
        )
        with self.assertRaisesRegex(ValueError, "unbound adapter test"):
            verify_evidence(self.rows(), evidence, root=self.root)

    def test_missing_handler_or_test_binding_fails(self):
        for field in ("backend_module", "service", "test_file"):
            evidence = self.evidence()
            evidence["listAccounts"][field] = "missing.py::symbol"
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "unbound"),
            ):
                verify_evidence(self.rows(), evidence, root=self.root)

    def test_evidence_cannot_read_outside_repository(self):
        evidence = self.evidence()
        evidence["listAccounts"]["file_sha256"] = {
            "../outside.py": {"sha256": "0" * 64}
        }
        with self.assertRaisesRegex(ValueError, "invalid evidence file"):
            verify_evidence(self.rows(), evidence, root=self.root)


if __name__ == "__main__":
    unittest.main()
