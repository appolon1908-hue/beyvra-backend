from contextlib import contextmanager
@contextmanager
def fault_scope(inject,cleanup):
    inject()
    try:yield
    finally:cleanup()
