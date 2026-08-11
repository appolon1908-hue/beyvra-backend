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

# Labels are deliberately bounded enums. Account, tenant, user, case, report,
# notification, transaction and provider identifiers must never be labels.
