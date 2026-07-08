"""
Provider registry infrastructure.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


class ProviderRegistrationError(ValueError):
    """Raised when provider registration fails."""


@dataclass(frozen=True)
class ProviderDescriptor:
    """Description of a registered provider."""

    name: str
    capabilities: Sequence[str] = field(default_factory=tuple)


class ProviderRegistry:
    """Register and query provider descriptors."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderDescriptor] = {}

    def register(self, provider: ProviderDescriptor) -> None:
        """Register a provider descriptor."""

        if not provider.name:
            raise ProviderRegistrationError("Provider name must not be empty.")
        if provider.name in self._providers:
            raise ProviderRegistrationError(f"Provider already registered: {provider.name}")
        self._providers[provider.name] = provider

    def get(self, name: str) -> ProviderDescriptor:
        """Return a registered provider by name."""

        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderRegistrationError(f"Provider is not registered: {name}") from exc

    def all(self) -> Sequence[ProviderDescriptor]:
        """Return all registered providers sorted by name."""

        return tuple(self._providers[name] for name in sorted(self._providers))

    def find_by_capability(self, capability: str) -> Sequence[ProviderDescriptor]:
        """Return providers that declare a capability."""

        matches: list[ProviderDescriptor] = []
        for provider in self.all():
            if capability in provider.capabilities:
                matches.append(provider)
        return tuple(matches)

    def extend(self, providers: Iterable[ProviderDescriptor]) -> None:
        """Register several providers."""

        for provider in providers:
            self.register(provider)
