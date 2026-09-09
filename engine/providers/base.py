from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class ProviderError(RuntimeError):
    """Provider failed without exposing provider-specific details to the pipeline."""


class Provider(ABC):
    name: str
    optional: bool = True

    @abstractmethod
    def healthcheck(self) -> bool:
        raise NotImplementedError


class ResearchProvider(Provider):
    @abstractmethod
    def research(self, topic: str) -> dict:
        raise NotImplementedError


class LLMProvider(Provider):
    @abstractmethod
    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError


class TTSProvider(Provider):
    @abstractmethod
    def synthesize(self, text: str, output: Path) -> float:
        """Write audio and return duration in seconds."""
        raise NotImplementedError


class MediaProvider(Provider):
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError


class VisualProvider(Provider):
    @abstractmethod
    def render(self, component: str, mode: str, payload: dict, output: Path) -> Path:
        raise NotImplementedError


class RendererProvider(Provider):
    @abstractmethod
    def render(self, manifest: dict, output: Path) -> Path:
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    purpose: str
    license: str
    free: bool
    api: bool
    gpu_required: bool
    github_actions: bool
    fallback: str | None
    rationale: str
