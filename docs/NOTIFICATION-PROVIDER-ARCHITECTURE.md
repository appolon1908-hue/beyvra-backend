# Notification provider architecture

`NotificationProvider` supports email, push, SMS, and in-app channels with idempotency and status lookup. Candidate transports include SES, SendGrid, Postmark, Twilio, and FCM. Privileged credentials are server-side only.

Financial notifications reflect authoritative events and can never create success state. Delivery fixtures cover send, retry, bounce, duplicate, and dead letter. Domain/security/provider approval remains external.

