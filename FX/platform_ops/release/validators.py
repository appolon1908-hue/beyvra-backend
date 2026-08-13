import re
SHA=re.compile(r"^[0-9a-f]{40,64}$")
def validate_manifest(values):
    required=("backend_sha","migration_hash","openapi_hash","sbom_hash","configuration_hash","feature_flag_policy_hash","test_evidence_hash","security_evidence_hash")
    missing=[k for k in required if not SHA.fullmatch(values.get(k,""))]
    if missing:raise ValueError("INVALID_OR_MISSING_HASH:"+",".join(missing))
    if any(not str(v).startswith("sha256:") for v in values.get("image_digests",{}).values()):raise ValueError("MUTABLE_IMAGE_REFERENCE")
    return True
