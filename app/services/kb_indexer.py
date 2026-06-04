"""Knowledge base — GridFS storage, tenant-scoped indexing."""

import logging
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from bson import ObjectId

from app.config import settings
from app.database import get_db
from app.services.platform_config import get_platform_config, update_platform_config
from app.services.prompt_files import read_knowledge_base_file

logger = logging.getLogger("enzo.kb")

MAX_TEXT_PER_DOC = 50_000
GRIDFS_BUCKET = "kb_files"


def _gridfs():
    db = get_db()
    return db[GRIDFS_BUCKET]


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return content.decode("utf-8", errors="ignore")[:MAX_TEXT_PER_DOC]
    if suffix == ".json":
        return content.decode("utf-8", errors="ignore")[:MAX_TEXT_PER_DOC]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError("pypdf is required for PDF uploads") from e
        reader = PdfReader(BytesIO(content))
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts)[:MAX_TEXT_PER_DOC]
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise RuntimeError("python-docx is required for DOCX uploads") from e
        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)[:MAX_TEXT_PER_DOC]
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_text_from_file(file_path: Path, filename: str) -> str:
    return extract_text_from_bytes(file_path.read_bytes(), filename)


def build_runtime_extra_knowledge(
    uploaded_docs: list[dict] | None = None,
    *,
    base_markdown: str = "",
) -> str:
    chunks = []
    base = (base_markdown or "").strip()
    if base:
        chunks.append(f"### knowledge_base.md\n{base}")
    if uploaded_docs:
        for doc in uploaded_docs:
            name = doc.get("name", "document")
            text = (doc.get("extractedText") or "").strip()
            if text:
                chunks.append(f"### {name}\n{text}")
    return "\n\n".join(chunks)


async def rebuild_extra_knowledge(tenant_id: str = "enculture") -> None:
    db = get_db()
    cfg = await get_platform_config(tenant_id)
    base_md = cfg.get("knowledge_base_markdown") or read_knowledge_base_file()
    cursor = db.kb_documents.find({"tenantId": tenant_id, "status": "indexed"})
    docs = await cursor.to_list(500)
    combined = build_runtime_extra_knowledge(docs, base_markdown=base_md)
    await db.platform_config.update_one(
        {"_id": tenant_id},
        {"$set": {"extra_knowledge": combined, "updatedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def save_kb_document(
    *,
    tenant_id: str,
    name: str,
    size_bytes: int,
    file_bytes: bytes,
    extracted_text: str,
    uploaded_by: ObjectId | None = None,
) -> str:
    db = get_db()
    gfs = _gridfs()
    now = datetime.now(timezone.utc)
    grid_id = await gfs.upload_from_stream(
        name,
        BytesIO(file_bytes),
        metadata={"tenantId": tenant_id, "contentType": name},
    )
    doc = {
        "tenantId": tenant_id,
        "name": name,
        "sizeBytes": size_bytes,
        "gridFsId": grid_id,
        "extractedText": extracted_text[:MAX_TEXT_PER_DOC],
        "status": "indexed",
        "uploadedBy": uploaded_by,
        "uploadedAt": now,
        "updatedAt": now,
    }
    result = await db.kb_documents.insert_one(doc)
    await rebuild_extra_knowledge(tenant_id)
    return str(result.inserted_id)


async def delete_kb_document(doc_id: str, tenant_id: str | None = None) -> bool:
    db = get_db()
    if not ObjectId.is_valid(doc_id):
        return False
    query: dict = {"_id": ObjectId(doc_id)}
    if tenant_id:
        query["tenantId"] = tenant_id
    doc = await db.kb_documents.find_one(query)
    if not doc:
        return False
    grid_id = doc.get("gridFsId")
    if grid_id:
        try:
            await _gridfs().delete(grid_id)
        except Exception as e:
            logger.warning("Could not delete GridFS file %s: %s", grid_id, e)
    legacy_path = doc.get("storedPath")
    if legacy_path:
        try:
            Path(legacy_path).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not delete legacy KB file %s: %s", legacy_path, e)
    tid = doc.get("tenantId", "enculture")
    await db.kb_documents.delete_one({"_id": ObjectId(doc_id)})
    await rebuild_extra_knowledge(tid)
    return True


def ensure_upload_dir() -> Path:
    """Legacy temp dir for migration script only."""
    upload_dir = Path(settings.admin_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


async def migrate_legacy_file_to_gridfs(doc: dict) -> None:
    """Upload legacy disk file to GridFS if storedPath exists."""
    path = doc.get("storedPath")
    if not path or doc.get("gridFsId"):
        return
    p = Path(path)
    if not p.exists():
        return
    content = p.read_bytes()
    gfs = _gridfs()
    grid_id = await gfs.upload_from_stream(doc.get("name", p.name), BytesIO(content))
    await get_db().kb_documents.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "gridFsId": grid_id,
                "tenantId": doc.get("tenantId") or "enculture",
            },
            "$unset": {"storedPath": ""},
        },
    )
