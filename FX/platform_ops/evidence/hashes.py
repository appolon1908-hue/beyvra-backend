import hashlib,json
def sha256_bytes(value):return hashlib.sha256(value).hexdigest()
def root_hash(values):return sha256_bytes(json.dumps(values,sort_keys=True,separators=(",",":")).encode())

MANIFEST_HASH_FIELDS=("candidate_hash","service_inventory_hash","config_hash","migration_hash","openapi_hash","sbom_hash","test_hash","chaos_hash","restore_hash","reconciliation_hash")
def manifest_root(manifest):return root_hash({field:getattr(manifest,field) for field in MANIFEST_HASH_FIELDS})
