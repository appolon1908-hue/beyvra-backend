import hashlib,json
def sha256_bytes(value):return hashlib.sha256(value).hexdigest()
def root_hash(values):return sha256_bytes(json.dumps(values,sort_keys=True,separators=(",",":")).encode())
