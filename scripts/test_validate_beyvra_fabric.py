import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
import validate_beyvra_fabric as validator


class FabricValidationTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(validator.OPENAPI_PATH.read_text())

    def validate_document(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'api.yaml'
            path.write_text(yaml.safe_dump(document))
            with patch.object(validator, 'OPENAPI_PATH', path):
                validator.validate_openapi()

    def test_current_contract(self):
        validator.main()

    def test_quoted_financial_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'api.yaml'
            source = validator.OPENAPI_PATH.read_text().replace('paths:\n', 'paths:\n  "/v1/automation/trades":\n    get:\n      operationId: harmless\n')
            path.write_text(source)
            with patch.object(validator, 'OPENAPI_PATH', path), self.assertRaises(SystemExit):
                validator.validate_openapi()

    def test_mutation_requires_body_and_safety_headers(self):
        for field in ('requestBody', 'parameters'):
            document = copy.deepcopy(self.document)
            del document['paths']['/v1/automation/onboarding-cases']['post'][field]
            with self.subTest(field=field), self.assertRaises(SystemExit):
                self.validate_document(document)

    def test_read_scope_is_required_for_get(self):
        document = copy.deepcopy(self.document)
        del document['paths']['/v1/automation/operations/{operation_id}']['get']['security']
        with self.assertRaises(SystemExit):
            self.validate_document(document)

    def test_machine_client_drift_is_rejected(self):
        manifest = json.loads(validator.N8N_MANIFEST_PATH.read_text())
        manifest['machine_client'] = 'different-client'
        original = validator.load_json
        with patch.object(validator, 'load_json', side_effect=lambda path: manifest if path == validator.N8N_MANIFEST_PATH else original(path)):
            with self.assertRaises(SystemExit):
                validator.validate_n8n_manifest()

    def test_duplicate_operation_ids_are_rejected(self):
        document = copy.deepcopy(self.document)
        document['paths']['/v1/automation/operations/{operation_id}']['get']['operationId'] = 'getReportRequest'
        with self.assertRaises(SystemExit):
            self.validate_document(document)
