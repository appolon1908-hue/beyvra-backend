from django.conf import settings


class ProviderCredentialMissing(RuntimeError):
    """Raised before network access when provider credentials are unavailable."""


def required_provider_credential(setting_name: str) -> str:
    value = str(getattr(settings, setting_name, "") or "").strip()
    if not value:
        raise ProviderCredentialMissing("PROVIDER_CREDENTIAL_MISSING")
    return value
