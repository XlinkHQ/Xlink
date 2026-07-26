from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.exceptions import ValidationError
from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.services import SettingsServiceDep
from app.schemas.settings import (
    NotificationSettingsRead,
    NotificationSettingsUpdate,
    SubscriptionSettingsRead,
    SubscriptionSettingsUpdate,
    WarpSettingsRead,
    WarpSettingsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class CoreTemplates(BaseModel):
    templates: dict[str, str]


class CoreTemplateUpdate(BaseModel):
    core: str
    template: str


@router.get("/subscription", response_model=SubscriptionSettingsRead)
async def get_subscription_settings(
    _admin: AdminUser,
    settings: SettingsServiceDep,
) -> SubscriptionSettingsRead:
    return SubscriptionSettingsRead.model_validate(await settings.get_subscription())


@router.patch("/subscription", response_model=SubscriptionSettingsRead)
async def update_subscription_settings(
    payload: SubscriptionSettingsUpdate,
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> SubscriptionSettingsRead:
    return SubscriptionSettingsRead.model_validate(await settings.update_subscription(payload))


@router.get("/notifications", response_model=NotificationSettingsRead)
async def get_notification_settings(
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> NotificationSettingsRead:
    return NotificationSettingsRead.model_validate(await settings.get_notifications())


@router.patch("/notifications", response_model=NotificationSettingsRead)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> NotificationSettingsRead:
    return NotificationSettingsRead.model_validate(await settings.update_notifications(payload))


@router.get("/warp", response_model=WarpSettingsRead)
async def get_warp_settings(
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> WarpSettingsRead:
    return WarpSettingsRead.model_validate(await settings.get_warp())


@router.patch("/warp", response_model=WarpSettingsRead)
async def update_warp_settings(
    payload: WarpSettingsUpdate,
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> WarpSettingsRead:
    return WarpSettingsRead.model_validate(await settings.update_warp(payload))


@router.post("/notifications/test")
async def test_notification_settings(
    payload: NotificationSettingsUpdate,
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> dict[str, str]:
    from app.core.config import get_settings
    from app.webhooks.dispatcher import WebhookDispatcher

    row = await settings.get_notifications()
    dispatcher = WebhookDispatcher(get_settings())
    dispatcher.apply_overrides(
        webhook_address=payload.webhook_address
        if payload.webhook_address is not None
        else row.webhook_address,
        discord_webhook_url=payload.discord_webhook_url
        if payload.discord_webhook_url is not None
        else row.discord_webhook_url,
        telegram_bot_token=payload.telegram_bot_token
        if payload.telegram_bot_token is not None
        else row.telegram_bot_token,
        telegram_chat_ids=payload.telegram_chat_ids
        if payload.telegram_chat_ids is not None
        else row.telegram_chat_ids,
    )
    if not dispatcher.enabled:
        raise ValidationError(
            "No channel configured — add a webhook, Discord or Telegram first.",
            code="no_channel",
        )
    try:
        await dispatcher.send_test()
    except ValueError as exc:
        raise ValidationError(str(exc), code="invalid_webhook") from exc
    return {"status": "sent"}


@router.get("/core", response_model=CoreTemplates)
async def get_core_templates(
    _admin: AdminUser,
    settings: SettingsServiceDep,
) -> CoreTemplates:
    return CoreTemplates(templates=await settings.get_core_templates())


@router.put("/core", response_model=CoreTemplates)
async def update_core_template(
    payload: CoreTemplateUpdate,
    _admin: SudoAdminUser,
    settings: SettingsServiceDep,
) -> CoreTemplates:
    return CoreTemplates(
        templates=await settings.update_core_template(payload.core, payload.template)
    )
