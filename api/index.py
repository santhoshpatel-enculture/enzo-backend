"""
Vercel serverless entry — ASGI adapter for the FastAPI app.

Deploy with Vercel project Root Directory = Enzo-backend.
"""

from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="auto")
