"""Direct webhook connections pinned to a freshly validated public address."""
import ipaddress
import socket
from urllib.parse import urlsplit

import requests
import urllib3
from django.conf import settings


class UnsafeWebhookDestination(requests.RequestException):
    pass


def resolve_destination(url):
    try:
        raw = urlsplit(url)
        if (raw.scheme not in {"http", "https"} or not raw.hostname
                or raw.username is not None or raw.password is not None
                or raw.fragment or "%" in raw.hostname or "\\" in url
                or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
            raise ValueError("invalid authority")
        if raw.port == 0:
            raise ValueError("invalid port")
        if raw.scheme != "https" and not settings.DEBUG:
            raise ValueError("HTTPS required")
        # Use the same URL normalization as the previous Requests transport.
        parsed = urlsplit(requests.Request("POST", url).prepare().url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        records = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not records:
            raise ValueError("empty DNS answer")
        addresses = []
        for record in records:
            address = ipaddress.ip_address(record[4][0])
            checked = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
            if ("%" in str(address) or (not settings.DEBUG and
                    (not checked.is_global or checked.is_multicast or checked.is_reserved))):
                raise ValueError("nonpublic destination")
            addresses.append(str(address))
        return parsed, port, addresses[0]
    except (ValueError, OSError, requests.RequestException) as exc:
        raise UnsafeWebhookDestination("Webhook destination could not be resolved safely.") from exc


def post_webhook(url, *, data, headers, timeout, allow_redirects=False):
    if allow_redirects:
        raise UnsafeWebhookDestination("Webhook redirects are prohibited.")
    parsed, port, address = resolve_destination(url)
    options = {"host": address, "port": port, "timeout": timeout, "maxsize": 1}
    if parsed.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            **options, server_hostname=parsed.hostname, assert_hostname=parsed.hostname,
            cert_reqs="CERT_REQUIRED", ca_certs=requests.certs.where(),
        )
    else:
        pool = urllib3.HTTPConnectionPool(**options)
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{port}"
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    response = None
    try:
        # A direct pool ignores environment proxies and connects only to the
        # numeric address above. No second hostname lookup, redirect or retry.
        response = pool.urlopen(
            "POST", target, body=data, headers={**headers, "Host": host},
            redirect=False, retries=False, assert_same_host=False,
            preload_content=False,
        )
        result = requests.Response()
        result.status_code = response.status
        result.url = parsed.geturl()
        return result
    except urllib3.exceptions.HTTPError as exc:
        raise requests.ConnectionError("Webhook transport failed") from exc
    finally:
        if response is not None:
            response.close()
        pool.close()
