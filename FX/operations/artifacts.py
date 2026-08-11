import os
from pathlib import Path
from uuid import UUID, uuid4

from django.conf import settings


def artifact_root():
    return Path(
        getattr(
            settings,
            "OPERATIONS_PRIVATE_ARTIFACT_ROOT",
            "/var/lib/beyvra/private-artifacts",
        )
    )


def write_private_artifact(*, namespace, suffix, content):
    """Write a private artifact and return an opaque, non-public reference."""
    if namespace not in {"reports", "privacy"} or suffix not in {"csv", "json"}:
        raise ValueError("Unsupported artifact type")
    root = artifact_root()
    directory = root / namespace
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    artifact_id = uuid4()
    relative_ref = f"{namespace}/{artifact_id}.{suffix}"
    final_path = root / relative_ref
    temporary_path = directory / f".{artifact_id}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary_path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as artifact:
            artifact.write(content)
            artifact.flush()
            os.fsync(artifact.fileno())
        os.replace(temporary_path, final_path)
        os.chmod(final_path, 0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return relative_ref


def open_private_artifact(reference):
    """Open only a well-formed artifact beneath the configured private root."""
    try:
        namespace, filename = reference.split("/", 1)
        stem, suffix = filename.rsplit(".", 1)
        UUID(stem)
    except (AttributeError, ValueError):
        raise FileNotFoundError("Invalid artifact reference")
    if namespace not in {"reports", "privacy"} or suffix not in {"csv", "json"}:
        raise FileNotFoundError("Invalid artifact reference")
    root = artifact_root().resolve()
    path = (root / namespace / filename).resolve()
    if root not in path.parents:
        raise FileNotFoundError("Invalid artifact reference")
    return path.open("rb")
