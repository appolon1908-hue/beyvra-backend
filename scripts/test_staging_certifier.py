import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import certify_staging_api as certifier


class StagingIdentityTests(unittest.TestCase):
    def test_missing_credentials_stop_before_network_or_evidence(self):
        for value in ("", "   "):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "evidence.json"
                with (
                    patch.dict(os.environ, {"BEYVRA_STAGING_ACCESS_TOKEN": value}),
                    patch("sys.argv", ["certify", "--output", str(output)]),
                    patch.object(certifier, "call") as call,
                ):
                    with self.assertRaisesRegex(SystemExit, "token|TOKEN"):
                        certifier.main()
                    call.assert_not_called()
                    self.assertFalse(output.exists())

    def test_provisioned_identity_reaches_probes_without_creating_session(self):
        class ProbeReached(Exception):
            pass

        with (
            patch.dict(
                os.environ, {"BEYVRA_STAGING_ACCESS_TOKEN": "isolated-test-token"}
            ),
            patch("sys.argv", ["certify", "--output", "unused-evidence.json"]),
            patch.object(certifier, "call", side_effect=ProbeReached) as call,
        ):
            with self.assertRaises(ProbeReached):
                certifier.main()
            self.assertEqual(call.call_args.args[1:3], ("GET", "/health/live"))
            self.assertEqual(call.call_args.kwargs["token"], "isolated-test-token")


if __name__ == "__main__":
    unittest.main()
