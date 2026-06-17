from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

JOB_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

_BLOCKED_IP_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def validate_job_id(job_id: str) -> str:
    if not JOB_ID_PATTERN.match(job_id):
        raise ValueError(
            "job_id must be 1-128 characters using letters, digits, underscores, or hyphens"
        )
    return job_id


def resolve_job_root(runs_dir: Path, job_id: str) -> Path:
    validated = validate_job_id(job_id)
    base = runs_dir.resolve()
    root = (base / validated).resolve()
    if not root.is_relative_to(base):
        raise ValueError("job_id must not escape the runs directory")
    return root


def validate_input_file(path: Path, *, max_bytes: int | None) -> None:
    if not path.exists():
        raise ValueError(f"Input file not found: {path}")
    if path.is_symlink():
        raise ValueError(f"Symlink inputs are not allowed: {path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a regular file: {path}")
    if max_bytes is not None:
        size = path.stat().st_size
        if size > max_bytes:
            raise ValueError(
                f"Input file exceeds maximum size ({size} bytes > {max_bytes} bytes): {path}"
            )


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address in network for network in _BLOCKED_IP_NETWORKS)


def assert_safe_webhook_url(url: str, *, https_only: bool = False) -> str:
    parsed = urlparse(url)
    if https_only and parsed.scheme != "https":
        raise ValueError("webhook_url must use https when webhook_https_only is enabled")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("webhook_url must start with http:// or https://")

    host = parsed.hostname
    if not host:
        raise ValueError("webhook_url must include a hostname")

    if host.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError("webhook_url must not target localhost")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_ip(literal):
            raise ValueError("webhook_url must not target private or reserved addresses")
        return url

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            resolved = ipaddress.ip_address(info[4][0])
            if _is_blocked_ip(resolved):
                raise ValueError("webhook_url must not target private or reserved addresses")
    except socket.gaierror as exc:
        raise ValueError(f"webhook_url hostname could not be resolved: {host}") from exc

    return url
