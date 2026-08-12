from prometheus_client import Counter, Gauge, Histogram

support_cases_open = Gauge("beyvra_support_cases_open", "Open support cases")
support_case_age = Histogram("beyvra_support_case_age_seconds", "Age of support cases")
support_first_response = Histogram("beyvra_support_first_response_seconds", "Time to first support response")
support_resolution = Histogram("beyvra_support_resolution_seconds", "Time to support resolution")
support_escalations = Counter("beyvra_support_escalations_total", "Support escalations", ("destination",))
notifications_created = Counter("beyvra_notifications_created_total", "Notifications created", ("category", "channel"))
notifications_sent = Counter("beyvra_notifications_sent_total", "Notifications sent", ("category", "channel"))
notifications_failed = Counter(
    "beyvra_notifications_failed_total", "Notification failures", ("category", "channel", "result")
)
notification_delivery = Histogram(
    "beyvra_notification_delivery_seconds", "Notification delivery time", ("category", "channel")
)
notification_dead_letter = Counter(
    "beyvra_notification_dead_letter_total", "Notification dead letters", ("category", "channel")
)
unauthorized_operator_attempts = Counter(
    "beyvra_operator_unauthorized_action_total", "Rejected operator actions", ("action",)
)
security_events = Counter(
    "beyvra_security_events_total", "Security events", ("reason", "risk")
)
freeze_enforcement_failures = Counter(
    "beyvra_freeze_enforcement_failures_total", "Freeze enforcement failures"
)
report_jobs_created = Counter(
    "beyvra_report_jobs_created_total", "Report jobs created", ("report_type",)
)
report_jobs_completed = Counter(
    "beyvra_report_jobs_completed_total", "Report jobs completed", ("report_type",)
)
report_jobs_failed = Counter(
    "beyvra_report_jobs_failed_total", "Report jobs failed", ("report_type",)
)
report_generation = Histogram(
    "beyvra_report_generation_seconds", "Report generation duration", ("report_type",)
)
privacy_exports_created = Counter(
    "beyvra_privacy_exports_created_total", "Privacy exports created"
)
privacy_exports_completed = Counter(
    "beyvra_privacy_exports_completed_total", "Privacy exports completed"
)
privacy_exports_failed = Counter(
    "beyvra_privacy_exports_failed_total", "Privacy exports failed"
)
privacy_export_generation = Histogram(
    "beyvra_privacy_export_generation_seconds", "Privacy export duration"
)
audit_integrity_failures = Counter(
    "beyvra_audit_integrity_failures_total", "Rejected audit integrity violations"
)

# Labels are deliberately bounded enums. Account, tenant, user, case, report,
# notification, transaction and provider identifiers must never be labels.
