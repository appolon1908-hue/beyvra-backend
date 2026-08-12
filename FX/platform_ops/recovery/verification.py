import hashlib
from pathlib import Path
def verify_file(path,expected_sha256):
    p=Path(path); digest=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return {"verified":digest==expected_sha256,"observed_sha256":digest}
