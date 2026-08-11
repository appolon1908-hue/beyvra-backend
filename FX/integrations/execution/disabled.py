class DisabledExecutionProvider:
    def _disabled(self, *_args, **_kwargs):
        raise RuntimeError("EXTERNAL_EXECUTION_DISABLED")
    submit_order = _disabled
    cancel_order = _disabled
    get_order = _disabled
    get_positions = _disabled
    def health(self):
        return {"state": "DISABLED"}
