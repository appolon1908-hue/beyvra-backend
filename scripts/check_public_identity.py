#!/usr/bin/env python3
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PUBLIC_FILES = (
    ".env.example",
    "docker-compose.yaml",
    "infra/realtime-v2/centrifugo.json",
    "nginx/nginx.prod.conf.template",
    "operations/check_nginx_upstreams.sh",
    "FX/payments/serializers.py",
    "FX/real_wallet/views.py",
    "FX/users/email_verification.py",
    "FX/users/utils.py",
    "FX/users/views.py",
    "FX/security/utils.py",
    "FX/wallet/utils.py",
    "FX/users/templates/user_ban_email.html",
    "FX/users/templates/device_info_alert_email.html",
    "FX/users/templates/email_verify_email.html",
    "FX/users/templates/password_reset_email.html",
    "FX/users/templates/welcome_email.html",
    "FX/security/templates/user_anomaly_info.html",
    "FX/wallet/templates/email_balance_update.html",
)
FORBIDDEN = re.compile(
    r"codestra\.cloud|tradx\.io|xtradx\.com|support@tradx\.com|\bTradx\b|\bTradex\b",
    re.IGNORECASE,
)


def main():
    violations = []
    for relative in ACTIVE_PUBLIC_FILES:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN.search(line):
                violations.append(f"{relative}:{line_number}")
    if violations:
        print("Legacy public identity remains in active surfaces:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    print(f"PUBLIC_IDENTITY_CHECK=PASS FILES={len(ACTIVE_PUBLIC_FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
