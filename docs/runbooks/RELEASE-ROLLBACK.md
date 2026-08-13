# Release rollback

Freeze new promotion, identify immutable release manifests, verify DB compatibility, restore approved image/config/flags, run readiness and synthetic smoke, then reconcile. Never reuse evidence across different hashes.
