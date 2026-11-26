'''
File:   __init__.py
Brief:  RAG module for participant B: PDF ingestion, hybrid index, search service.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Standalone FastAPI module for the "Digital Mechanic" hackathon project.
Lives next to the backend without touching it: the backend (src/mechanic)
calls this service over HTTP via ``RAG_API_URL`` (see shared/models.py for
the contract). Run the service with ``uvicorn rag.service:app --port 8003``.
'''
