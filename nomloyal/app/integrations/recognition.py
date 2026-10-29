"""Recognition provider interface (optional, consent-based, OFF by default).

NomLoyal does NOT ship a face-recognition engine and never pretends to recognise anyone. A real provider
(an SDK or a local service that you have licensed and validated) can be added by implementing
RecognitionProvider and registering it in PROVIDERS. Rules every provider must follow:

* only customers with recorded, current biometric consent may be enrolled or matched;
* unknown people / bystanders are never identified or stored;
* raw face images are not stored; templates, if the provider needs them, stay inside the provider's own
  protected storage and are deleted with delete();
* every match is a suggestion: below the confidence threshold it is ignored, and with confirmation enabled a
  staff member must confirm it before anything is recorded;
* accuracy depends on camera angle, lighting, resolution and occlusion - validate on site before use.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Match:
    customer_id: int
    confidence: float


class RecognitionProvider(ABC):
    name = "provider"

    @abstractmethod
    def available(self) -> tuple[bool, str]: ...

    @abstractmethod
    def enroll(self, customer_id: int, frames: list) -> None: ...

    @abstractmethod
    def match(self, frame) -> list[Match]: ...

    @abstractmethod
    def delete(self, customer_id: int) -> None: ...


class NoProvider(RecognitionProvider):
    """Default: recognition is not installed. Every method refuses."""
    name = "none"

    def available(self) -> tuple[bool, str]:
        return False, ("No recognition provider is installed. Use loyalty ID, QR code or phone lookup. "
                       "See docs/RECOGNITION_PROVIDERS.md to add a validated provider.")

    def enroll(self, customer_id, frames):
        raise RuntimeError("No recognition provider installed.")

    def match(self, frame):
        return []

    def delete(self, customer_id):
        return None


PROVIDERS: dict[str, type[RecognitionProvider]] = {"none": NoProvider}


def get_provider(name: str) -> RecognitionProvider:
    return PROVIDERS.get(name or "none", NoProvider)()


def accept_match(m: Match, threshold: float, consented: set[int]) -> bool:
    """A provider match is usable only above the threshold and only for consenting, enrolled customers."""
    return m.confidence >= threshold and m.customer_id in consented
