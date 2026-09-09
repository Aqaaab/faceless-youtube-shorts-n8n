from __future__ import annotations

from dataclasses import dataclass

from .base import Provider, ProviderError


@dataclass
class ProviderRegistry:
    _providers: dict[str, dict[str, Provider]]

    def __init__(self) -> None:
        self._providers = {}

    def register(self, capability: str, provider: Provider) -> None:
        self._providers.setdefault(capability, {})[provider.name] = provider

    def get(self, capability: str, name: str) -> Provider:
        try:
            return self._providers[capability][name]
        except KeyError as exc:
            raise ProviderError(f"Provider not registered: {capability}/{name}") from exc

    def first_healthy(self, capability: str, preferred: list[str] | None = None) -> Provider:
        providers = self._providers.get(capability, {})
        order = preferred or list(providers)
        for name in order:
            provider = providers.get(name)
            if provider and provider.healthcheck():
                return provider
        raise ProviderError(f"No healthy provider available for capability: {capability}")
