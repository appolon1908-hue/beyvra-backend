#!/usr/bin/env python3
"""Run the complete Beyvra signed read-only release chain from one manual click.

The orchestrator never builds in production, never enables live-effect flags, and
fails closed when a workflow run, digest, attestation-backed certification,
rollback result, protected-main SHA, or paired backend/frontend identity differs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlencode

BACKEND_REPOSITORY = os.environ.get(
    "BACKEND_REPOSITORY", "appolon1908-hue/beyvra-backend"
)
FRONTEND_REPOSITORY = os.environ.get(
    "FRONTEND_REPOSITORY", "appolon1908-hue/beyvra-frontend"
)

BACKEND_DEPLOY_WORKFLOW = "deploy.yml"
BACKEND_CERTIFY_WORKFLOW = "certify-deployment.yml"
BACKEND_PROMOTE_WORKFLOW = "promote-production-readonly.yml"
FRONTEND_DEPLOY_WORKFLOW = "deploy.yml"
FRONTEND_CERTIFY_WORKFLOW = "certify-deployment.yml"
FRONTEND_PROMOTE_WORKFLOW = "promote-production-readonly.yml"

SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")
CHANGE = re.compile(r"^[A-Za-z0-9._-]+$")
RUN_ID = re.compile(r"^[0-9]+$")

POLL_SECONDS = max(2, int(os.environ.get("BEYVRA_RELEASE_POLL_SECONDS", "10")))
DISCOVERY_TIMEOUT_SECONDS = int(
    os.environ.get("BEYVRA_RELEASE_DISCOVERY_TIMEOUT_SECONDS", "1200")
)
RUN_TIMEOUT_SECONDS = int(
    os.environ.get("BEYVRA_RELEASE_RUN_TIMEOUT_SECONDS", "20400")
)


class ReleaseError(RuntimeError):
    """A fail-closed release condition."""


@dataclass(frozen=True)
class WorkflowRun:
    repository: str
    workflow: str
    run_id: int
    head_sha: str
    event: str
    status: str
    conclusion: str | None
    html_url: str
    created_at: str

    @classmethod
    def from_api(cls, repository: str, workflow: str, value: Mapping[str, Any]) -> "WorkflowRun":
        return cls(
            repository=repository,
            workflow=workflow,
            run_id=int(value["id"]),
            head_sha=str(value.get("head_sha", "")),
            event=str(value.get("event", "")),
            status=str(value.get("status", "")),
            conclusion=(
                None
                if value.get("conclusion") is None
                else str(value.get("conclusion"))
            ),
            html_url=str(value.get("html_url", "")),
            created_at=str(value.get("created_at", "")),
        )


def log(message: str) -> None:
    print(f"[beyvra-go-live] {message}", flush=True)


def run_command(
    command: list[str],
    *,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log(f"run: {shlex.join(command)}")
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=capture,
        env=os.environ.copy(),
    )
    if check and completed.returncode != 0:
        stdout = completed.stdout.strip() if completed.stdout else ""
        stderr = completed.stderr.strip() if completed.stderr else ""
        detail = "\n".join(part for part in (stdout, stderr) if part)
        raise ReleaseError(
            f"command failed ({completed.returncode}): {shlex.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return completed


def gh_api_json(
    endpoint: str,
    *,
    method: str = "GET",
    fields: Mapping[str, str] | None = None,
) -> dict[str, Any] | list[Any]:
    command = ["gh", "api"]
    if method != "GET":
        command.extend(["--method", method])
    command.append(endpoint)
    for key, value in (fields or {}).items():
        command.extend(["-f", f"{key}={value}"])
    completed = run_command(command)
    text = completed.stdout.strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, (dict, list)):
        raise ReleaseError(f"unexpected GitHub API response for {endpoint}")
    return value


def gh_api_optional(endpoint: str) -> dict[str, Any] | list[Any] | None:
    command = ["gh", "api", endpoint]
    completed = run_command(command, check=False)
    if completed.returncode == 0:
        text = completed.stdout.strip()
        return json.loads(text) if text else {}
    stderr = completed.stderr or ""
    if "HTTP 404" in stderr or "Not Found" in stderr:
        return None
    raise ReleaseError(
        f"GitHub API lookup failed: {endpoint}\n{stderr.strip()}"
    )


def repository_endpoint(repository: str, suffix: str) -> str:
    return f"repos/{repository}/{suffix.lstrip('/')}"


def main_sha(repository: str) -> str:
    value = gh_api_json(repository_endpoint(repository, "commits/main"))
    if not isinstance(value, dict):
        raise ReleaseError(f"invalid main-commit response for {repository}")
    sha = str(value.get("sha", ""))
    if not SHA.fullmatch(sha):
        raise ReleaseError(f"invalid protected-main SHA for {repository}: {sha!r}")
    return sha


def assert_main_sha(repository: str, expected: str) -> None:
    observed = main_sha(repository)
    if observed != expected:
        raise ReleaseError(
            f"protected main moved for {repository}: expected {expected}, observed {observed}"
        )


def require_repository_file(repository: str, path: str) -> None:
    encoded = quote(path, safe="/")
    value = gh_api_optional(
        repository_endpoint(repository, f"contents/{encoded}?ref=main")
    )
    if value is None:
        raise ReleaseError(f"required protected-main file is missing: {repository}:{path}")


def read_repository_json(repository: str, path: str) -> dict[str, Any] | None:
    encoded = quote(path, safe="/")
    value = gh_api_optional(
        repository_endpoint(repository, f"contents/{encoded}?ref=main")
    )
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ReleaseError(f"unexpected contents response for {repository}:{path}")
    raw = value.get("content")
    encoding = value.get("encoding")
    if not isinstance(raw, str) or encoding != "base64":
        raise ReleaseError(f"unable to decode {repository}:{path}")
    document = json.loads(base64.b64decode(raw).decode("utf-8"))
    if not isinstance(document, dict):
        raise ReleaseError(f"JSON root is not an object: {repository}:{path}")
    return document


def require_manual_only_intent(repository: str) -> None:
    intent = read_repository_json(repository, ".release/intent.json")
    if intent is not None and intent.get("enabled") is True:
        raise ReleaseError(
            f"automatic release intent is enabled in {repository}; one-click mode requires it disabled"
        )


def require_green_checks(repository: str, sha: str, required: Iterable[str]) -> None:
    value = gh_api_json(
        repository_endpoint(repository, f"commits/{sha}/check-runs?per_page=100")
    )
    if not isinstance(value, dict):
        raise ReleaseError(f"invalid check-run response for {repository}@{sha}")
    runs = value.get("check_runs")
    if not isinstance(runs, list):
        raise ReleaseError(f"check runs are missing for {repository}@{sha}")
    observed = {
        str(item.get("name")): str(item.get("conclusion"))
        for item in runs
        if isinstance(item, dict)
    }
    missing = [name for name in required if observed.get(name) != "success"]
    if missing:
        raise ReleaseError(
            f"protected-main checks are not green for {repository}@{sha}: "
            + ", ".join(f"{name}={observed.get(name, 'missing')}" for name in missing)
        )


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def list_workflow_runs(
    repository: str,
    workflow: str,
    *,
    event: str,
) -> list[WorkflowRun]:
    query = urlencode({"per_page": "100", "branch": "main", "event": event})
    workflow_id = quote(workflow, safe="")
    value = gh_api_json(
        repository_endpoint(
            repository,
            f"actions/workflows/{workflow_id}/runs?{query}",
        )
    )
    if not isinstance(value, dict) or not isinstance(value.get("workflow_runs"), list):
        raise ReleaseError(f"invalid workflow-run response for {repository}:{workflow}")
    return [
        WorkflowRun.from_api(repository, workflow, item)
        for item in value["workflow_runs"]
        if isinstance(item, dict)
    ]


def workflow_run_ids(repository: str, workflow: str, *, event: str) -> set[int]:
    return {run.run_id for run in list_workflow_runs(repository, workflow, event=event)}


def dispatch_workflow(
    repository: str,
    workflow: str,
    inputs: Mapping[str, str],
) -> None:
    fields = {"ref": "main"}
    fields.update({f"inputs[{name}]": value for name, value in inputs.items()})
    workflow_id = quote(workflow, safe="")
    gh_api_json(
        repository_endpoint(repository, f"actions/workflows/{workflow_id}/dispatches"),
        method="POST",
        fields=fields,
    )


def discover_new_run(
    repository: str,
    workflow: str,
    *,
    event: str,
    before_ids: set[int],
    expected_head_sha: str,
    started_at: datetime,
) -> WorkflowRun:
    deadline = time.monotonic() + DISCOVERY_TIMEOUT_SECONDS
    earliest = started_at - timedelta(seconds=5)
    while time.monotonic() < deadline:
        candidates = [
            run
            for run in list_workflow_runs(repository, workflow, event=event)
            if run.run_id not in before_ids
            and run.head_sha == expected_head_sha
            and parse_time(run.created_at) >= earliest
        ]
        if len(candidates) == 1:
            run = candidates[0]
            log(
                f"discovered {repository}:{workflow} run {run.run_id}: {run.html_url}"
            )
            return run
        if len(candidates) > 1:
            ids = ", ".join(str(run.run_id) for run in candidates)
            raise ReleaseError(
                f"ambiguous new workflow runs for {repository}:{workflow}: {ids}"
            )
        time.sleep(POLL_SECONDS)
    raise ReleaseError(f"new workflow run was not discovered: {repository}:{workflow}")


def get_run(repository: str, run_id: int, workflow: str) -> WorkflowRun:
    value = gh_api_json(repository_endpoint(repository, f"actions/runs/{run_id}"))
    if not isinstance(value, dict):
        raise ReleaseError(f"invalid workflow run response: {repository}#{run_id}")
    return WorkflowRun.from_api(repository, workflow, value)


def wait_for_success(run: WorkflowRun) -> WorkflowRun:
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    last_status = ""
    while time.monotonic() < deadline:
        current = get_run(run.repository, run.run_id, run.workflow)
        status_text = f"{current.status}/{current.conclusion or '-'}"
        if status_text != last_status:
            log(
                f"{current.repository}:{current.workflow} run {current.run_id} "
                f"is {status_text}: {current.html_url}"
            )
            last_status = status_text
        if current.status == "completed":
            if current.conclusion != "success":
                raise ReleaseError(
                    f"workflow failed closed: {current.repository}:{current.workflow} "
                    f"run {current.run_id} concluded {current.conclusion}: {current.html_url}"
                )
            return current
        time.sleep(POLL_SECONDS)
    raise ReleaseError(
        f"workflow did not complete within the orchestration window: {run.html_url}"
    )


def dispatch_and_wait(
    repository: str,
    workflow: str,
    *,
    inputs: Mapping[str, str],
    expected_head_sha: str,
) -> tuple[WorkflowRun, datetime]:
    before = workflow_run_ids(repository, workflow, event="workflow_dispatch")
    started = datetime.now(timezone.utc)
    log(f"dispatching {repository}:{workflow}")
    dispatch_workflow(repository, workflow, inputs)
    run = discover_new_run(
        repository,
        workflow,
        event="workflow_dispatch",
        before_ids=before,
        expected_head_sha=expected_head_sha,
        started_at=started,
    )
    return wait_for_success(run), started


def discover_automatic_and_wait(
    repository: str,
    workflow: str,
    *,
    before_ids: set[int],
    expected_head_sha: str,
    started_at: datetime,
) -> WorkflowRun:
    run = discover_new_run(
        repository,
        workflow,
        event="workflow_run",
        before_ids=before_ids,
        expected_head_sha=expected_head_sha,
        started_at=started_at,
    )
    return wait_for_success(run)


def download_artifact(
    repository: str,
    run_id: int,
    artifact_name: str,
    destination: Path,
) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "gh",
            "run",
            "download",
            str(run_id),
            "--repo",
            repository,
            "--name",
            artifact_name,
            "--dir",
            str(destination),
        ]
    )


def unique_file(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise ReleaseError(
            f"expected exactly one {name} in {root}, found {len(matches)}"
        )
    return matches[0]


def load_json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON root must be an object: {path}")
    return value


def verify_checksum(manifest: Path, checksum_file: Path) -> None:
    tokens = checksum_file.read_text(encoding="utf-8").split()
    if not tokens or not re.fullmatch(r"[0-9a-f]{64}", tokens[0]):
        raise ReleaseError(f"invalid checksum file: {checksum_file}")
    observed = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if observed != tokens[0]:
        raise ReleaseError(f"manifest checksum mismatch: {manifest}")


def require_exact(value: Mapping[str, Any], expected: Mapping[str, Any], context: str) -> None:
    mismatches = [
        f"{key}={value.get(key)!r} (expected {wanted!r})"
        for key, wanted in expected.items()
        if value.get(key) != wanted
    ]
    if mismatches:
        raise ReleaseError(f"{context} mismatch: " + "; ".join(mismatches))


def validate_backend_certification(
    value: Mapping[str, Any],
    *,
    target: str,
    source_sha: str,
    backend_image: str | None,
    edge_image: str | None,
    deploy_run_id: int,
    certification_run_id: int,
) -> tuple[str, str]:
    require_exact(
        value,
        {
            "schema_version": 1,
            "source_sha": source_sha,
            "target": target,
            "deploy_run_id": str(deploy_run_id),
            "certification_run_id": str(certification_run_id),
            "certification_result": "PASS",
            "rollback_rehearsal": "PASS",
            "zero_live_effects": "PASS",
            "deployment_read_only": True,
            "live_trading_authorized": False,
            "real_money_authorized": False,
            "payments_authorized": False,
            "withdrawals_authorized": False,
            "transactional_email_authorized": False,
            "external_execution_authorized": False,
        },
        f"backend {target} certification",
    )
    observed_backend = str(value.get("backend_image", ""))
    observed_edge = str(value.get("edge_image", ""))
    if not IMAGE.fullmatch(observed_backend) or not IMAGE.fullmatch(observed_edge):
        raise ReleaseError("backend certification contains a non-immutable image")
    if backend_image is not None and observed_backend != backend_image:
        raise ReleaseError("backend digest changed between staging and production")
    if edge_image is not None and observed_edge != edge_image:
        raise ReleaseError("edge digest changed between staging and production")
    return observed_backend, observed_edge


def validate_frontend_certification(
    value: Mapping[str, Any],
    *,
    target: str,
    source_sha: str,
    frontend_image: str | None,
    backend_source_sha: str,
    backend_image: str,
    backend_certification_run_id: int,
    deploy_run_id: int,
    certification_run_id: int,
) -> str:
    require_exact(
        value,
        {
            "schema_version": 1,
            "source_sha": source_sha,
            "backend_source_sha": backend_source_sha,
            "backend_image": backend_image,
            "backend_certification_run_id": str(backend_certification_run_id),
            "target": target,
            "deploy_run_id": str(deploy_run_id),
            "certification_run_id": str(certification_run_id),
            "certification_result": "PASS",
            "rollback_rehearsal": "PASS",
            "paired_backend_certification": "PASS",
            "signed_provenance_verified": True,
            "deployment_read_only": True,
            "live_trading_authorized": False,
            "real_money_authorized": False,
            "payments_authorized": False,
            "withdrawals_authorized": False,
            "transactional_email_authorized": False,
            "external_execution_authorized": False,
            "legacy_realtime_fallback_enabled": False,
        },
        f"frontend {target} certification",
    )
    observed_frontend = str(value.get("frontend_image", ""))
    if not IMAGE.fullmatch(observed_frontend):
        raise ReleaseError("frontend certification contains a non-immutable image")
    if frontend_image is not None and observed_frontend != frontend_image:
        raise ReleaseError("frontend digest changed between staging and production")
    return observed_frontend


def load_backend_certification_artifact(
    *,
    run: WorkflowRun,
    change_id: str,
    target: str,
    source_sha: str,
    backend_image: str | None,
    edge_image: str | None,
    deploy_run_id: int,
    root: Path,
) -> tuple[dict[str, Any], str, str]:
    destination = root / f"backend-{target}-certification"
    download_artifact(
        BACKEND_REPOSITORY,
        run.run_id,
        f"beyvra-backend-certification-{target}-{change_id}",
        destination,
    )
    predicate_path = unique_file(destination, "certification-attestation-predicate.json")
    predicate = load_json_file(predicate_path)
    observed_backend, observed_edge = validate_backend_certification(
        predicate,
        target=target,
        source_sha=source_sha,
        backend_image=backend_image,
        edge_image=edge_image,
        deploy_run_id=deploy_run_id,
        certification_run_id=run.run_id,
    )
    if target == "staging-readonly":
        promotion = unique_file(destination, "production-promotion-manifest.json")
        checksum = unique_file(destination, "production-promotion-manifest.json.sha256")
        verify_checksum(promotion, checksum)
        require_exact(
            load_json_file(promotion),
            predicate,
            "backend staging promotion manifest",
        )
    return predicate, observed_backend, observed_edge


def load_frontend_certification_artifact(
    *,
    run: WorkflowRun,
    change_id: str,
    target: str,
    source_sha: str,
    frontend_image: str | None,
    backend_source_sha: str,
    backend_image: str,
    backend_certification_run_id: int,
    deploy_run_id: int,
    root: Path,
) -> tuple[dict[str, Any], str]:
    destination = root / f"frontend-{target}-certification"
    download_artifact(
        FRONTEND_REPOSITORY,
        run.run_id,
        f"beyvra-frontend-certification-{target}-{change_id}",
        destination,
    )
    predicate_path = unique_file(destination, "certification-attestation-predicate.json")
    predicate = load_json_file(predicate_path)
    observed_frontend = validate_frontend_certification(
        predicate,
        target=target,
        source_sha=source_sha,
        frontend_image=frontend_image,
        backend_source_sha=backend_source_sha,
        backend_image=backend_image,
        backend_certification_run_id=backend_certification_run_id,
        deploy_run_id=deploy_run_id,
        certification_run_id=run.run_id,
    )
    if target == "staging-readonly":
        promotion = unique_file(destination, "production-promotion-manifest.json")
        checksum = unique_file(destination, "production-promotion-manifest.json.sha256")
        verify_checksum(promotion, checksum)
        require_exact(
            load_json_file(promotion),
            predicate,
            "frontend staging promotion manifest",
        )
    return predicate, observed_frontend


def workflow_url(repository: str, workflow: str) -> str:
    return f"https://github.com/{repository}/actions/workflows/{workflow}"


def preflight() -> tuple[str, str]:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise ReleaseError("BEYVRA_RELEASE_BOT_TOKEN is missing")
    if os.environ.get("GITHUB_REPOSITORY") not in {None, "", BACKEND_REPOSITORY}:
        raise ReleaseError("one-click workflow must run from the authoritative backend repository")

    backend_sha = main_sha(BACKEND_REPOSITORY)
    frontend_sha = main_sha(FRONTEND_REPOSITORY)

    backend_files = (
        ".github/workflows/deploy.yml",
        ".github/workflows/certify-deployment.yml",
        ".github/workflows/promote-production-readonly.yml",
        "operations/inspect_deployment_run.sh",
        "operations/run_deployment_certification.sh",
    )
    frontend_files = (
        ".github/workflows/deploy.yml",
        ".github/workflows/certify-deployment.yml",
        ".github/workflows/promote-production-readonly.yml",
        "operations/verify_backend_certification.sh",
        "operations/rehearse_frontend_rollback.sh",
    )
    for path in backend_files:
        require_repository_file(BACKEND_REPOSITORY, path)
    for path in frontend_files:
        require_repository_file(FRONTEND_REPOSITORY, path)

    require_manual_only_intent(BACKEND_REPOSITORY)
    require_manual_only_intent(FRONTEND_REPOSITORY)

    require_green_checks(
        BACKEND_REPOSITORY,
        backend_sha,
        ("container", "secrets", "validate", "certification-static"),
    )
    require_green_checks(
        FRONTEND_REPOSITORY,
        frontend_sha,
        ("container", "secrets", "validate", "certification-static"),
    )

    log(f"preflight PASS: backend={backend_sha}, frontend={frontend_sha}")
    return backend_sha, frontend_sha


def execute_release() -> dict[str, Any]:
    backend_sha, frontend_sha = preflight()
    github_run_id = os.environ.get("GITHUB_RUN_ID", "manual")
    github_run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    change_root = f"beyvra-readonly-{github_run_id}-{github_run_attempt}"
    if not CHANGE.fullmatch(change_root):
        raise ReleaseError(f"generated change identifier is invalid: {change_root}")

    backend_staging_change = f"{change_root}-backend-staging"
    backend_production_change = f"{change_root}-backend-production"
    frontend_staging_change = f"{change_root}-frontend-staging"
    frontend_production_change = f"{change_root}-frontend-production"

    summary: dict[str, Any] = {
        "schema_version": 1,
        "orchestrator_run_id": github_run_id,
        "orchestrator_run_attempt": github_run_attempt,
        "backend_repository": BACKEND_REPOSITORY,
        "frontend_repository": FRONTEND_REPOSITORY,
        "backend_source_sha": backend_sha,
        "frontend_source_sha": frontend_sha,
        "deployment_read_only": True,
        "canary_traffic_maximum_percent": 1,
        "live_effects_authorized": False,
        "status": "IN_PROGRESS",
        "runs": {},
    }

    with tempfile.TemporaryDirectory(prefix="beyvra-go-live-") as temporary:
        evidence_root = Path(temporary)

        # 1. Build once, sign, deploy, certify, and roll back backend staging.
        assert_main_sha(BACKEND_REPOSITORY, backend_sha)
        backend_stage_cert_before = workflow_run_ids(
            BACKEND_REPOSITORY,
            BACKEND_CERTIFY_WORKFLOW,
            event="workflow_run",
        )
        backend_stage_deploy, backend_stage_started = dispatch_and_wait(
            BACKEND_REPOSITORY,
            BACKEND_DEPLOY_WORKFLOW,
            inputs={
                "source_sha": backend_sha,
                "target": "staging-readonly",
                "publish_images": "true",
                "backend_image": "",
                "edge_image": "",
                "deploy": "true",
                "change_id": backend_staging_change,
                "allow_schema_migrations": "false",
                "migration_compatibility_approved": "false",
            },
            expected_head_sha=backend_sha,
        )
        backend_stage_cert = discover_automatic_and_wait(
            BACKEND_REPOSITORY,
            BACKEND_CERTIFY_WORKFLOW,
            before_ids=backend_stage_cert_before,
            expected_head_sha=backend_sha,
            started_at=backend_stage_started,
        )
        (
            _backend_stage_predicate,
            backend_image,
            edge_image,
        ) = load_backend_certification_artifact(
            run=backend_stage_cert,
            change_id=backend_staging_change,
            target="staging-readonly",
            source_sha=backend_sha,
            backend_image=None,
            edge_image=None,
            deploy_run_id=backend_stage_deploy.run_id,
            root=evidence_root,
        )

        # 2. Promote the same backend digests to production read-only and certify.
        assert_main_sha(BACKEND_REPOSITORY, backend_sha)
        backend_prod_deploy_before = workflow_run_ids(
            BACKEND_REPOSITORY,
            BACKEND_DEPLOY_WORKFLOW,
            event="workflow_dispatch",
        )
        backend_prod_cert_before = workflow_run_ids(
            BACKEND_REPOSITORY,
            BACKEND_CERTIFY_WORKFLOW,
            event="workflow_run",
        )
        backend_promote, backend_promote_started = dispatch_and_wait(
            BACKEND_REPOSITORY,
            BACKEND_PROMOTE_WORKFLOW,
            inputs={
                "certification_run_id": str(backend_stage_cert.run_id),
                "change_id": backend_production_change,
                "deploy": "true",
            },
            expected_head_sha=backend_sha,
        )
        backend_prod_deploy = discover_new_run(
            BACKEND_REPOSITORY,
            BACKEND_DEPLOY_WORKFLOW,
            event="workflow_dispatch",
            before_ids=backend_prod_deploy_before,
            expected_head_sha=backend_sha,
            started_at=backend_promote_started,
        )
        backend_prod_deploy = wait_for_success(backend_prod_deploy)
        backend_prod_cert = discover_automatic_and_wait(
            BACKEND_REPOSITORY,
            BACKEND_CERTIFY_WORKFLOW,
            before_ids=backend_prod_cert_before,
            expected_head_sha=backend_sha,
            started_at=backend_promote_started,
        )
        load_backend_certification_artifact(
            run=backend_prod_cert,
            change_id=backend_production_change,
            target="production-readonly",
            source_sha=backend_sha,
            backend_image=backend_image,
            edge_image=edge_image,
            deploy_run_id=backend_prod_deploy.run_id,
            root=evidence_root,
        )

        # 3. Build once, sign, deploy, certify, and roll back frontend staging,
        # bound to the exact signed backend staging certification.
        assert_main_sha(BACKEND_REPOSITORY, backend_sha)
        assert_main_sha(FRONTEND_REPOSITORY, frontend_sha)
        frontend_stage_cert_before = workflow_run_ids(
            FRONTEND_REPOSITORY,
            FRONTEND_CERTIFY_WORKFLOW,
            event="workflow_run",
        )
        frontend_stage_deploy, frontend_stage_started = dispatch_and_wait(
            FRONTEND_REPOSITORY,
            FRONTEND_DEPLOY_WORKFLOW,
            inputs={
                "source_sha": frontend_sha,
                "target": "staging-readonly",
                "publish_image": "true",
                "frontend_image": "",
                "backend_source_sha": backend_sha,
                "backend_image": backend_image,
                "backend_certification_run_id": str(backend_stage_cert.run_id),
                "deploy": "true",
                "change_id": frontend_staging_change,
            },
            expected_head_sha=frontend_sha,
        )
        frontend_stage_cert = discover_automatic_and_wait(
            FRONTEND_REPOSITORY,
            FRONTEND_CERTIFY_WORKFLOW,
            before_ids=frontend_stage_cert_before,
            expected_head_sha=frontend_sha,
            started_at=frontend_stage_started,
        )
        (
            _frontend_stage_predicate,
            frontend_image,
        ) = load_frontend_certification_artifact(
            run=frontend_stage_cert,
            change_id=frontend_staging_change,
            target="staging-readonly",
            source_sha=frontend_sha,
            frontend_image=None,
            backend_source_sha=backend_sha,
            backend_image=backend_image,
            backend_certification_run_id=backend_stage_cert.run_id,
            deploy_run_id=frontend_stage_deploy.run_id,
            root=evidence_root,
        )

        # 4. Promote the same frontend digest only after the exact backend
        # production read-only certification has passed.
        assert_main_sha(BACKEND_REPOSITORY, backend_sha)
        assert_main_sha(FRONTEND_REPOSITORY, frontend_sha)
        frontend_prod_deploy_before = workflow_run_ids(
            FRONTEND_REPOSITORY,
            FRONTEND_DEPLOY_WORKFLOW,
            event="workflow_dispatch",
        )
        frontend_prod_cert_before = workflow_run_ids(
            FRONTEND_REPOSITORY,
            FRONTEND_CERTIFY_WORKFLOW,
            event="workflow_run",
        )
        frontend_promote, frontend_promote_started = dispatch_and_wait(
            FRONTEND_REPOSITORY,
            FRONTEND_PROMOTE_WORKFLOW,
            inputs={
                "frontend_staging_certification_run_id": str(
                    frontend_stage_cert.run_id
                ),
                "backend_production_certification_run_id": str(
                    backend_prod_cert.run_id
                ),
                "change_id": frontend_production_change,
                "deploy": "true",
            },
            expected_head_sha=frontend_sha,
        )
        frontend_prod_deploy = discover_new_run(
            FRONTEND_REPOSITORY,
            FRONTEND_DEPLOY_WORKFLOW,
            event="workflow_dispatch",
            before_ids=frontend_prod_deploy_before,
            expected_head_sha=frontend_sha,
            started_at=frontend_promote_started,
        )
        frontend_prod_deploy = wait_for_success(frontend_prod_deploy)
        frontend_prod_cert = discover_automatic_and_wait(
            FRONTEND_REPOSITORY,
            FRONTEND_CERTIFY_WORKFLOW,
            before_ids=frontend_prod_cert_before,
            expected_head_sha=frontend_sha,
            started_at=frontend_promote_started,
        )
        load_frontend_certification_artifact(
            run=frontend_prod_cert,
            change_id=frontend_production_change,
            target="production-readonly",
            source_sha=frontend_sha,
            frontend_image=frontend_image,
            backend_source_sha=backend_sha,
            backend_image=backend_image,
            backend_certification_run_id=backend_prod_cert.run_id,
            deploy_run_id=frontend_prod_deploy.run_id,
            root=evidence_root,
        )

        assert_main_sha(BACKEND_REPOSITORY, backend_sha)
        assert_main_sha(FRONTEND_REPOSITORY, frontend_sha)

        run_values = {
            "backend_staging_deploy": backend_stage_deploy,
            "backend_staging_certification": backend_stage_cert,
            "backend_production_promotion": backend_promote,
            "backend_production_deploy": backend_prod_deploy,
            "backend_production_certification": backend_prod_cert,
            "frontend_staging_deploy": frontend_stage_deploy,
            "frontend_staging_certification": frontend_stage_cert,
            "frontend_production_promotion": frontend_promote,
            "frontend_production_deploy": frontend_prod_deploy,
            "frontend_production_certification": frontend_prod_cert,
        }
        summary["runs"] = {
            name: {
                "repository": run.repository,
                "workflow": run.workflow,
                "run_id": run.run_id,
                "url": run.html_url,
                "conclusion": "success",
            }
            for name, run in run_values.items()
        }
        summary.update(
            {
                "backend_image": backend_image,
                "edge_image": edge_image,
                "frontend_image": frontend_image,
                "backend_staging_certification_run_id": backend_stage_cert.run_id,
                "backend_production_certification_run_id": backend_prod_cert.run_id,
                "frontend_staging_certification_run_id": frontend_stage_cert.run_id,
                "frontend_production_certification_run_id": frontend_prod_cert.run_id,
                "status": "PASS",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return summary


def write_summary(summary: Mapping[str, Any]) -> Path:
    output = Path(
        os.environ.get(
            "BEYVRA_RELEASE_SUMMARY_PATH", "one-click-readonly-release-summary.json"
        )
    )
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        lines = [
            "# Beyvra one-click read-only go-live",
            "",
            f"**Result:** `{summary.get('status')}`",
            f"**Backend source:** `{summary.get('backend_source_sha')}`",
            f"**Backend image:** `{summary.get('backend_image')}`",
            f"**Edge image:** `{summary.get('edge_image')}`",
            f"**Frontend source:** `{summary.get('frontend_source_sha')}`",
            f"**Frontend image:** `{summary.get('frontend_image')}`",
            "**Production mode:** read-only, maximum 1% canary",
            "**Live effects:** not authorized",
            "",
            "## Workflow evidence",
        ]
        runs = summary.get("runs", {})
        if isinstance(runs, dict):
            for name, value in runs.items():
                if isinstance(value, dict):
                    lines.append(f"- [{name}]({value.get('url')}) — success")
        with Path(step_summary).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return output


def self_test() -> None:
    backend = {
        "schema_version": 1,
        "source_sha": "a" * 40,
        "backend_image": "ghcr.io/example/backend@sha256:" + "b" * 64,
        "edge_image": "ghcr.io/example/backend-edge@sha256:" + "c" * 64,
        "target": "staging-readonly",
        "deploy_run_id": "101",
        "certification_run_id": "102",
        "certification_result": "PASS",
        "rollback_rehearsal": "PASS",
        "zero_live_effects": "PASS",
        "deployment_read_only": True,
        "live_trading_authorized": False,
        "real_money_authorized": False,
        "payments_authorized": False,
        "withdrawals_authorized": False,
        "transactional_email_authorized": False,
        "external_execution_authorized": False,
    }
    backend_image, _ = validate_backend_certification(
        backend,
        target="staging-readonly",
        source_sha="a" * 40,
        backend_image=None,
        edge_image=None,
        deploy_run_id=101,
        certification_run_id=102,
    )
    frontend = {
        "schema_version": 1,
        "source_sha": "d" * 40,
        "frontend_image": "ghcr.io/example/frontend@sha256:" + "e" * 64,
        "backend_source_sha": "a" * 40,
        "backend_image": backend_image,
        "backend_certification_run_id": "102",
        "target": "staging-readonly",
        "deploy_run_id": "103",
        "certification_run_id": "104",
        "certification_result": "PASS",
        "rollback_rehearsal": "PASS",
        "paired_backend_certification": "PASS",
        "signed_provenance_verified": True,
        "deployment_read_only": True,
        "live_trading_authorized": False,
        "real_money_authorized": False,
        "payments_authorized": False,
        "withdrawals_authorized": False,
        "transactional_email_authorized": False,
        "external_execution_authorized": False,
        "legacy_realtime_fallback_enabled": False,
    }
    validate_frontend_certification(
        frontend,
        target="staging-readonly",
        source_sha="d" * 40,
        frontend_image=None,
        backend_source_sha="a" * 40,
        backend_image=backend_image,
        backend_certification_run_id=102,
        deploy_run_id=103,
        certification_run_id=104,
    )
    unsafe = dict(frontend)
    unsafe["live_trading_authorized"] = True
    try:
        validate_frontend_certification(
            unsafe,
            target="staging-readonly",
            source_sha="d" * 40,
            frontend_image=None,
            backend_source_sha="a" * 40,
            backend_image=backend_image,
            backend_certification_run_id=102,
            deploy_run_id=103,
            certification_run_id=104,
        )
    except ReleaseError:
        pass
    else:
        raise ReleaseError("self-test accepted unsafe frontend certification")
    log("self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        summary = execute_release()
        output = write_summary(summary)
        log(f"complete PASS: {output}")
        return 0
    except (ReleaseError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"BEYVRA_ONE_CLICK_GO_LIVE=FAIL: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
