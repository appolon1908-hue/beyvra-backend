from celery import shared_task


@shared_task
def print_ok():
    """A side-effect-free worker health probe."""

    return "ok"
