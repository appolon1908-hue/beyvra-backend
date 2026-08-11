# Surveillance Replay

`python manage.py replay_surveillance <sanitized-json>` evaluates chronological synthetic events and prints findings. It writes no cases, restrictions, alerts, inbox, outbox or normal surveillance events. Replay output is explicitly marked `replay=true` and `mutations=0`.
