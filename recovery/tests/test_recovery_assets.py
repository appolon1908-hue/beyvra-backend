import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class RecoveryAssetsTests(unittest.TestCase):
    def test_verifier_fails_closed_without_isolation_gate(self):
        result = subprocess.run([str(ROOT / "scripts/disaster-recovery-verify.sh")], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 20)
        self.assertIn("BEYVRA_DR_ISOLATED=1", result.stderr)

    def test_verifier_refuses_real_money_flags(self):
        result = subprocess.run(
            [str(ROOT / "scripts/disaster-recovery-verify.sh")], cwd=ROOT,
            env={"PATH": "/usr/bin:/bin", "BEYVRA_DR_ISOLATED": "1", "REAL_MONEY_ENABLED": "true"},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 21)
        self.assertIn("REAL_MONEY_ENABLED", result.stderr)

    def test_network_is_internal_and_images_are_pinned_to_major_minor(self):
        compose = (ROOT / "recovery/docker-compose.yml").read_text()
        self.assertIn("internal: true", compose)
        self.assertIn("recovery/postgres.Dockerfile", compose)
        self.assertIn("redis:7.4-alpine", compose)
        self.assertIn("nats:2.11-alpine", compose)

    def test_authority_and_pitr_gap_are_explicit(self):
        inventory = (ROOT / "docs/DISASTER-RECOVERY-INVENTORY.md").read_text()
        self.assertIn("Redis is never authoritative", inventory)
        self.assertIn("PITR_READINESS=DOCUMENTED_GAP", inventory)
        self.assertIn("RPO_TARGET_SECONDS=300", inventory)

    def test_backup_alerts_cover_all_failure_modes(self):
        alerts = (ROOT / "monitoring/prometheus/beyvra-backup-alerts.yml").read_text()
        for name in ("BeyvraBackupStale", "BeyvraBackupFailed", "BeyvraBackupChecksumFailed", "BeyvraRestoreVerificationStale"):
            self.assertIn(name, alerts)

    def test_verifier_rejects_corrupt_compose_and_nats_configuration(self):
        verifier = (ROOT / "scripts/disaster-recovery-verify.sh").read_text()
        self.assertIn("invalid Compose configuration unexpectedly validated", verifier)
        self.assertIn("invalid NATS configuration unexpectedly validated", verifier)
        self.assertIn("nats:2.11-alpine -t -c", verifier)

    def test_verifier_runs_restored_simulation_and_realtime_contracts(self):
        verifier = (ROOT / "scripts/disaster-recovery-verify.sh").read_text()
        self.assertIn("apps.trading.tests.test_simulated_e2e ws.test_v2", verifier)
        self.assertIn("RESTORED_SYSTEM_E2E=PASS", verifier)


if __name__ == "__main__":
    unittest.main()
