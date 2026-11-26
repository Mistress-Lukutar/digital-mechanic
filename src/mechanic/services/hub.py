'''
File:   hub.py
Brief:  ServiceHub - all backend services wired together for tool access.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Created once at application startup and handed to every tool executor via
ToolContext.services; API routes use the same instance.
'''

from __future__ import annotations

from dataclasses import dataclass

from mechanic.config import Settings
from mechanic.services.fleet import FleetStore
from mechanic.services.ml_client import MlClient
from mechanic.services.rag_client import ManualManifest, RagClient
from mechanic.services.toir_client import ToirClient


@dataclass
class ServiceHub:
    '''Bundle of live services shared across the application.'''

    settings: Settings
    fleet: FleetStore
    ml: MlClient
    toir: ToirClient
    rag: RagClient
    manifest: ManualManifest
    ticket_log: object  # services.ticket_log.TicketLog (Stage 4)
    usage: object  # services.usage.UsageLog (Stage 4)
