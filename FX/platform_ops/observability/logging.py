SENSITIVE_KEYS={"password","secret","token","authorization","credential","private_key","api_key"}
def redact(value):
    if isinstance(value,dict):return {k:("[REDACTED]" if any(x in k.lower() for x in SENSITIVE_KEYS) else redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [redact(x) for x in value]
    return value
