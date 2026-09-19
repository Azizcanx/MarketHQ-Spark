# -*- coding: utf-8 -*-
"""Phase J9 — Provider Registry + Model Registry."""

from __future__ import annotations

from ai_gateway.models import ProviderSpec, ModelSpec, ProviderState, Tier


class ProviderRegistry:
    """Centralized provider registry with health tracking."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> None:
        self._providers[spec.provider_id] = spec

    def get(self, provider_id: str) -> ProviderSpec | None:
        return self._providers.get(provider_id)

    def list_all(self) -> list[ProviderSpec]:
        return list(self._providers.values())

    def list_available(self) -> list[ProviderSpec]:
        return [p for p in self._providers.values()
                if p.enabled and p.state == ProviderState.AVAILABLE]

    def list_by_tier(self, tier: Tier) -> list[ProviderSpec]:
        return [p for p in self._providers.values() if p.tier == tier and p.enabled]

    def list_free(self) -> list[ProviderSpec]:
        return self.list_by_tier(Tier.FREE)

    def list_paid(self) -> list[ProviderSpec]:
        return self.list_by_tier(Tier.PAID)

    def disable(self, provider_id: str) -> None:
        if provider_id in self._providers:
            self._providers[provider_id].enabled = False
            self._providers[provider_id].state = ProviderState.DISABLED

    def enable(self, provider_id: str) -> None:
        if provider_id in self._providers:
            self._providers[provider_id].enabled = True
            if self._providers[provider_id].state == ProviderState.DISABLED:
                self._providers[provider_id].state = ProviderState.AVAILABLE

    def set_state(self, provider_id: str, state: ProviderState) -> None:
        if provider_id in self._providers:
            self._providers[provider_id].state = state

    def update_health(self, provider_id: str, state: ProviderState,
                       error: str = "") -> None:
        if provider_id in self._providers:
            p = self._providers[provider_id]
            p.state = state
            if error:
                p.last_error = error
            if state == ProviderState.AVAILABLE:
                p.last_success = ""
            else:
                p.last_error = error

    def remove(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def count(self) -> int:
        return len(self._providers)

    def to_dict(self) -> dict[str, dict]:
        return {pid: p.to_dict() for pid, p in self._providers.items()}


class ModelRegistry:
    """Centralized model registry."""

    def __init__(self) -> None:
        self._models: dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        self._models[spec.model_id] = spec

    def get(self, model_id: str) -> ModelSpec | None:
        return self._models.get(model_id)

    def list_all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def list_by_provider(self, provider_id: str) -> list[ModelSpec]:
        return [m for m in self._models.values() if m.provider_id == provider_id]

    def list_by_tier(self, tier: Tier) -> list[ModelSpec]:
        return [m for m in self._models.values() if m.tier == tier and m.enabled]

    def list_free(self) -> list[ModelSpec]:
        return self.list_by_tier(Tier.FREE)

    def list_paid(self) -> list[ModelSpec]:
        return self.list_by_tier(Tier.PAID)

    def list_available(self) -> list[ModelSpec]:
        return [m for m in self._models.values() if m.enabled and m.availability]

    def disable(self, model_id: str) -> None:
        if model_id in self._models:
            self._models[model_id].enabled = False

    def enable(self, model_id: str) -> None:
        if model_id in self._models:
            self._models[model_id].enabled = True

    def has_capability(self, model_id: str, capability: str) -> bool:
        m = self._models.get(model_id)
        if not m:
            return False
        return capability in m.capabilities

    def count(self) -> int:
        return len(self._models)

    def to_dict(self) -> dict[str, dict]:
        return {mid: m.to_dict() for mid, m in self._models.items()}