"""Subscription CRUD service."""

from __future__ import annotations

from uuid import UUID

from backend.azure_api.subscriptions.repository import Subscription, SubscriptionRepository
from backend.common.contracts.models import NotificationSubscription
from backend.common.providers.interfaces import Clock, IdGenerator


class SubscriptionNotFound(LookupError):
    """The requested subscription is absent from the authenticated owner partition."""


class SubscriptionConflict(RuntimeError):
    """The caller attempted to replace a stale subscription version."""


class SubscriptionService:
    def __init__(
        self,
        *,
        repository: SubscriptionRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ids = ids

    def create(self, *, owner_sub: str, email: str, tags: list[str]) -> Subscription:
        normalized_email, normalized_tags = self._normalize(email=email, tags=tags)
        now = self._clock.now_utc()
        subscription = Subscription(
            subscription_id=self._ids.new_uuid(),
            owner_sub=owner_sub,
            email=normalized_email,
            tags=normalized_tags,
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._repository.create(subscription)
        return subscription

    def list(self, *, owner_sub: str) -> list[Subscription]:
        return self._repository.list_for_owner(owner_sub)

    def update(
        self,
        *,
        owner_sub: str,
        subscription_id: UUID,
        email: str,
        tags: list[str],
        expected_version: int,
    ) -> Subscription:
        current = self._repository.get(owner_sub, subscription_id)
        if current is None:
            raise SubscriptionNotFound("subscription was not found")
        normalized_email, normalized_tags = self._normalize(email=email, tags=tags)
        updated = Subscription(
            subscription_id=current.subscription_id,
            owner_sub=current.owner_sub,
            email=normalized_email,
            tags=normalized_tags,
            status=current.status,
            version=expected_version + 1,
            created_at=current.created_at,
            updated_at=self._clock.now_utc(),
        )
        if not self._repository.replace(updated, expected_version=expected_version):
            raise SubscriptionConflict("subscription version has changed")
        return updated

    def delete(self, *, owner_sub: str, subscription_id: UUID) -> bool:
        return self._repository.delete(owner_sub, subscription_id)

    @staticmethod
    def _normalize(*, email: str, tags: list[str]) -> tuple[str, tuple[str, ...]]:
        normalized_tags = tuple(sorted({tag.strip().casefold() for tag in tags if tag.strip()}))
        normalized_email = email.strip().casefold()
        validated = NotificationSubscription(email=normalized_email, tags=list(normalized_tags))
        return validated.email, tuple(validated.tags)
