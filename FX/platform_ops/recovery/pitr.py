def assess(settings):
    required=("archive_mode","archive_command","restore_command")
    missing=[k for k in required if not settings.get(k)]
    return {"status":"PASS" if not missing else "EXTERNAL_INFRASTRUCTURE_BLOCKED","missing":missing}
