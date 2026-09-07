import uuid

from reference_data.models import Instrument


class InstrumentResolutionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def resolve_active_instrument(reference):
    """Resolve exactly one active canonical instrument without venue guessing."""

    value = str(reference or "").strip()
    if not value:
        raise InstrumentResolutionError("INSTRUMENT_REQUIRED")

    try:
        instrument_id = uuid.UUID(value)
    except (TypeError, ValueError):
        instrument_id = None

    if instrument_id is not None:
        instrument = Instrument.objects.filter(
            instrument_id=instrument_id,
            status=Instrument.Status.ACTIVE,
        ).first()
        if instrument is None:
            raise InstrumentResolutionError("INSTRUMENT_UNAVAILABLE")
        return instrument

    matches = list(
        Instrument.objects.filter(
            canonical_symbol=value.upper(),
            status=Instrument.Status.ACTIVE,
        ).order_by("instrument_id")[:2]
    )
    if not matches:
        raise InstrumentResolutionError("INSTRUMENT_UNAVAILABLE")
    if len(matches) > 1:
        raise InstrumentResolutionError("INSTRUMENT_AMBIGUOUS")
    return matches[0]
