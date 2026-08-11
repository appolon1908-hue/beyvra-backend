from .provider import ExecutionProvider


class DisabledExecutionProvider(ExecutionProvider):
    def _disabled(self, *_args, **_kwargs):
        raise RuntimeError("EXTERNAL_EXECUTION_DISABLED")
    submit_order = _disabled
    cancel_order = _disabled
    replace_order = _disabled
    get_order = _disabled
    list_orders = _disabled
    get_executions = _disabled
    resolve_unknown_operation = _disabled
    preview_order = _disabled
    def capabilities(self): return {"mode":"DISABLED","network":False}
    def health(self):
        return {"state": "DISABLED"}
