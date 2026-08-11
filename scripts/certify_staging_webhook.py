#!/usr/bin/env python3
"""Fixture-only staging webhook contract verifier; never uses production secrets."""

import argparse
import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def post(url, body, headers):
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        response = urlopen(request, timeout=15)
        return response.status, json.loads(response.read().decode())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("BEYVRA_STAGING_BASE_URL", "https://staging.beyvra.com"))
    parser.add_argument("--provider", default="fixture")
    parser.add_argument("--purpose", default="notification")
    args = parser.parse_args()
    secret = os.getenv("BEYVRA_STAGING_WEBHOOK_TEST_SECRET", "")
    if "staging" not in args.base_url.lower() or args.provider not in {"fixture", "test"}:
        raise SystemExit("Refusing non-staging or non-fixture webhook certification")
    if not secret:
        raise SystemExit("BEYVRA_STAGING_WEBHOOK_TEST_SECRET is required")
    body = json.dumps({"type": "delivery.updated", "fixture": True}, separators=(",", ":")).encode()
    event_id, timestamp = f"fixture-{uuid.uuid4()}", int(time.time())
    signed = f"{args.provider}.{args.purpose}.{timestamp}.{event_id}.".encode() + body
    headers = {"X-Beyvra-Timestamp": str(timestamp), "X-Beyvra-Event-ID": event_id, "X-Beyvra-Signature": hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()}
    url = f"{args.base_url.rstrip('/')}/api/v1/webhooks/{args.provider}/{args.purpose}"
    first = post(url, body, headers)
    duplicates = [post(url, body, headers) for _ in range(99)]
    invalid = post(url, body, {**headers, "X-Beyvra-Signature": "invalid"})
    passed = first[0] == 202 and all(item[0] == 200 and item[1].get("status") == "duplicate" for item in duplicates) and invalid[0] == 401
    print(json.dumps({"valid": first[0], "duplicates": len(duplicates), "invalid_signature": invalid[0], "business_effects": 1 if passed else "UNKNOWN", "result": "PASS" if passed else "FAIL"}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
