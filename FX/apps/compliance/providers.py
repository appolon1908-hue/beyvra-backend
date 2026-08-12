from abc import ABC, abstractmethod

class ComplianceProvider(ABC):
    @abstractmethod
    def create_session(self, subject_ref): ...
    @abstractmethod
    def get_session(self, session_ref): ...
    @abstractmethod
    def get_verification(self, verification_ref): ...
    @abstractmethod
    def screen_identity(self, subject_ref): ...
    @abstractmethod
    def health(self): ...
    @abstractmethod
    def capabilities(self): ...

class DisabledComplianceProvider(ComplianceProvider):
    def _disabled(self, *_args): raise RuntimeError("PROVIDER_NOT_AVAILABLE")
    create_session = get_session = get_verification = screen_identity = _disabled
    def health(self): return {"status": "DISABLED"}
    def capabilities(self): return []
