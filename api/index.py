"""
Vercel serverless entry — ASGI FastAPI app.

Vercel's Python runtime detects a top-level `app` in api/index.py (not Mangum).
Deploy with project Root Directory = repository root (enzo-backend repo).
"""

from app.main import app
