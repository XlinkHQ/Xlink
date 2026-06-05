from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.agent.commands import CommandSigner
from app.agent.healing import HealingPolicy
from app.agent.service import NodeAgentService
from app.backup.service import BackupService
from app.dependencies.core import (
    CacheDep,
    DatabaseDep,
    EventsDep,
    ProvidersDep,
    SessionDep,
    SettingsDep,
)
from app.failover.service import FailoverService
from app.gitops.service import GitOpsService
from app.monitoring.service import MonitoringService
from app.repositories.client_assignment import ClientAssignmentRepository
from app.repositories.node import NodeRepository
from app.repositories.profile import ProfileRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.scheduler.service import SmartSchedulerService
from app.services.auth_service import AuthService
from app.services.client_assignment_service import ClientAssignmentService
from app.services.node_service import NodeService
from app.services.profile_service import ProfileService
from app.services.token_service import TokenService
from app.services.user_service import UserService
from app.subscription.generator import SubscriptionGenerator
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.repository import SubscriptionRepository
from app.subscription.service import SubscriptionService
from app.traffic.service import TrafficService


def get_user_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repo(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_node_repo(session: SessionDep) -> NodeRepository:
    return NodeRepository(session)


def get_profile_repo(session: SessionDep) -> ProfileRepository:
    return ProfileRepository(session)


def get_assignment_repo(session: SessionDep) -> ClientAssignmentRepository:
    return ClientAssignmentRepository(session)


def get_subscription_repo(session: SessionDep) -> SubscriptionRepository:
    return SubscriptionRepository(session)


def get_node_agent_service(
    session: SessionDep,
    events: EventsDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> NodeAgentService:
    return NodeAgentService(
        session,
        events=events,
        signer=CommandSigner(settings.agent_signing_secret),
        cache=cache,
        healing_policy=HealingPolicy(enabled=settings.agent_self_healing_enabled),
    )


UserRepoDep = Annotated[UserRepository, Depends(get_user_repo)]
RefreshTokenRepoDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repo)]
NodeRepoDep = Annotated[NodeRepository, Depends(get_node_repo)]
ProfileRepoDep = Annotated[ProfileRepository, Depends(get_profile_repo)]
AssignmentRepoDep = Annotated[ClientAssignmentRepository, Depends(get_assignment_repo)]
SubscriptionRepoDep = Annotated[SubscriptionRepository, Depends(get_subscription_repo)]
NodeAgentServiceDep = Annotated[NodeAgentService, Depends(get_node_agent_service)]


def get_user_service(repo: UserRepoDep, cache: CacheDep) -> UserService:
    return UserService(repo, cache)


def get_token_service(repo: RefreshTokenRepoDep, settings: SettingsDep) -> TokenService:
    return TokenService(repo, settings)


def get_node_service(repo: NodeRepoDep) -> NodeService:
    return NodeService(repo)


def get_profile_service(
    repo: ProfileRepoDep,
    node_repo: NodeRepoDep,
    providers: ProvidersDep,
) -> ProfileService:
    return ProfileService(repo, node_repo, providers)


def get_assignment_service(
    repo: AssignmentRepoDep,
    user_repo: UserRepoDep,
    profile_repo: ProfileRepoDep,
    node_repo: NodeRepoDep,
    providers: ProvidersDep,
) -> ClientAssignmentService:
    return ClientAssignmentService(repo, user_repo, profile_repo, node_repo, providers)


def get_subscription_service(
    repo: SubscriptionRepoDep,
    providers: ProvidersDep,
    cache: CacheDep,
) -> SubscriptionService:
    return SubscriptionService(
        repo,
        SubscriptionGenerator(providers),
        SubscriptionRenderer(),
        cache,
    )


def get_traffic_service(session: SessionDep, events: EventsDep) -> TrafficService:
    return TrafficService(session, events=events)


def get_monitoring_service(
    session: SessionDep,
    providers: ProvidersDep,
    cache: CacheDep,
) -> MonitoringService:
    return MonitoringService(session, providers, cache=cache)


def get_scheduler_service(
    session: SessionDep,
    providers: ProvidersDep,
) -> SmartSchedulerService:
    return SmartSchedulerService(session, providers)


def get_failover_service(
    db: DatabaseDep,
    providers: ProvidersDep,
    events: EventsDep,
) -> FailoverService:
    return FailoverService(db, providers, events)


def get_backup_service(session: SessionDep) -> BackupService:
    return BackupService(session)


def get_gitops_service(session: SessionDep) -> GitOpsService:
    return GitOpsService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
NodeServiceDep = Annotated[NodeService, Depends(get_node_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
AssignmentServiceDep = Annotated[ClientAssignmentService, Depends(get_assignment_service)]
SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]
TrafficServiceDep = Annotated[TrafficService, Depends(get_traffic_service)]
MonitoringServiceDep = Annotated[MonitoringService, Depends(get_monitoring_service)]
SchedulerServiceDep = Annotated[SmartSchedulerService, Depends(get_scheduler_service)]
FailoverServiceDep = Annotated[FailoverService, Depends(get_failover_service)]
BackupServiceDep = Annotated[BackupService, Depends(get_backup_service)]
GitOpsServiceDep = Annotated[GitOpsService, Depends(get_gitops_service)]


def get_auth_service(
    user_service: UserServiceDep,
    token_service: TokenServiceDep,
) -> AuthService:
    return AuthService(user_service, token_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
