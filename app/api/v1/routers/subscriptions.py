from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies.auth import AdminUser
from app.dependencies.services import SubscriptionServiceDep
from app.subscription.schemas import (
    ConfigRead,
    FeedRead,
    FeedRequest,
    FeedScope,
    RenderVersion,
    SubscriptionFormat,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _request(
    scope: FeedScope,
    subject_id: uuid.UUID,
    feed_format: SubscriptionFormat,
    version: RenderVersion,
    use_cache: bool,
) -> FeedRequest:
    return FeedRequest(
        scope=scope,
        subject_id=subject_id,
        format=feed_format,
        version=version,
        use_cache=use_cache,
    )


@router.get("/assignments/{assignment_id}/config", response_model=ConfigRead)
async def assignment_config(
    assignment_id: uuid.UUID,
    _admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
) -> ConfigRead:
    return await subscriptions.generate_config(assignment_id)


@router.get("/assignments/{assignment_id}/feed", response_model=FeedRead)
async def assignment_feed(
    assignment_id: uuid.UUID,
    _admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    return await subscriptions.feed(
        _request(FeedScope.ASSIGNMENT, assignment_id, format, version, use_cache)
    )


@router.get("/profiles/{profile_id}/feed", response_model=FeedRead)
async def profile_feed(
    profile_id: uuid.UUID,
    _admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    return await subscriptions.feed(
        _request(FeedScope.PROFILE, profile_id, format, version, use_cache)
    )


@router.get("/users/{user_id}/feed", response_model=FeedRead)
async def user_feed(
    user_id: uuid.UUID,
    _admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    return await subscriptions.feed(_request(FeedScope.USER, user_id, format, version, use_cache))
