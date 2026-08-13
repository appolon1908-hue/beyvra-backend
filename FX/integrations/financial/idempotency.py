def financial_idempotency_key(*, command, resource_id, request_id):
    return f"{command}:{resource_id}:{request_id}"
