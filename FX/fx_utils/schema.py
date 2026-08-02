"""OpenAPI helpers for legacy DRF views.

Some older APIViews return hand-built ``Response`` objects and do not declare a
serializer.  They are still valid endpoints, but drf-spectacular otherwise
drops their request/response body from the generated contract.  The hook keeps
every endpoint in the schema with a conservative JSON response shape until a
view-specific serializer is added.
"""

from rest_framework import serializers


class GenericApiResponseSerializer(serializers.Serializer):
    """Fallback shape for legacy endpoints that return arbitrary JSON."""

    detail = serializers.CharField(required=False)
    data = serializers.JSONField(required=False)


def add_legacy_serializer_fallback(endpoints):
    """Attach a schema-only fallback serializer to undocumented APIViews."""

    for _path, _path_regex, _method, callback in endpoints:
        view_class = getattr(callback, "cls", None)
        if view_class is None:
            continue
        if getattr(view_class, "serializer_class", None) is not None:
            continue
        # Several third-party views (including SimpleJWT refresh) select their
        # serializer through get_serializer_class instead of a class attribute.
        # Never replace those: doing so would change live request handling after
        # the schema endpoint is visited.
        try:
            selected = view_class().get_serializer_class()
        except Exception:
            selected = None
        if selected is None:
            callback.cls = type(
                f"{view_class.__name__}Schema",
                (view_class,),
                {"serializer_class": GenericApiResponseSerializer},
            )
    return endpoints
