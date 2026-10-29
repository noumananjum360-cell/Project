"""Camera interface. The app works fully without any camera."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CameraStatus:
    running: bool = False
    connected: bool = False
    fps: float = 0.0
    message: str = "Stopped"


class CameraSource(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def latest(self):
        """Newest frame (BGR numpy array) or None."""

    @abstractmethod
    def status(self) -> CameraStatus: ...
