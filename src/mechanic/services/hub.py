'''
File:   hub.py
Brief:  ServiceHub - all backend services wired together for tool access.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Created once at application startup and handed to every tool executor via
ToolContext.services; API routes use the same instance. Tests build hubs
manually with the same constructor.
'''

from __future__ import annotations

from dataclasses import dataclass

from mechanic.config import Settings
from mechanic.services.alerts import AlertsStore
from mechanic.services.auth import AuthService
from mechanic.services.chats import ChatStore
from mechanic.services.fleet import FleetStore
from mechanic.services.ml_client import MlClient
from mechanic.services.rag_client import ManualManifest, RagClient
from mechanic.services.ticket_log import TicketLog
from mechanic.services.toir_client import ToirClient
from mechanic.services.usage import UsageLog


@dataclass
class ServiceHub:
    '''Bundle of live services shared across the application.'''

    settings: Settings
    fleet: FleetStore
    ml: MlClient
    toir: ToirClient
    rag: RagClient
    manifest: ManualManifest
    ticket_log: TicketLog
    chats: ChatStore
    usage: UsageLog
    alerts: AlertsStore
    auth: AuthService


def build_service_hub(settings: Settings) -> ServiceHub:
    '''Construct every service from settings.

    Args:
        settings: Application settings (data dir, service URLs, DB path).

    Returns:
        A fully wired ServiceHub.
    '''
    return ServiceHub(
        settings=settings,
        fleet=FleetStore(settings.app_data_dir),
        ml=MlClient(settings.ml_api_url),
        toir=ToirClient(settings.toir_api_url),
        rag=RagClient(
            base_url=settings.rag_api_url,
            mock_chunks_path=settings.mock_chunks_path,
            manuals_dir=settings.manuals_dir,
        ),
        manifest=ManualManifest(settings.manuals_dir),
        ticket_log=TicketLog(settings.resolve_db_path()),
        chats=ChatStore(settings.resolve_db_path()),
        usage=UsageLog(settings.resolve_db_path()),
        alerts=AlertsStore(settings.resolve_db_path()),
        auth=AuthService(settings.resolve_db_path()),
    )
