import logging
import httpx
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import List, Optional, Dict, Any

logger = logging.getLogger('ats_resume_scorer')

from backend.core.config import SUPABASE_URL, SUPABASE_KEY

LOCAL_DB_PATH = Path(__file__).resolve().parents[2] / '.local' / 'ats_score.sqlite3'

def _get_headers():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _use_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _ensure_local_db() -> None:
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LOCAL_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_email TEXT DEFAULT '',
                filename TEXT NOT NULL,
                ats_score REAL DEFAULT 0,
                keyword_match REAL DEFAULT 0,
                missing_keywords TEXT DEFAULT '[]',
                resume_text TEXT DEFAULT '',
                job_description TEXT DEFAULT '',
                analysis_result TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                email TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                event_type TEXT NOT NULL DEFAULT 'login',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _local_execute(query: str, params: tuple = ()) -> sqlite3.Cursor:
    _ensure_local_db()
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(query, params)
    conn.commit()
    conn.close()
    return cur


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def _serializable_result(analysis_result: Dict) -> Dict[str, Any]:
    return json.loads(json.dumps(_serialize(analysis_result), default=str))

def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _safe_excerpt(text: str, limit: int = 5000) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


async def save_analysis(
    user_id: str,
    filename: str,
    analysis_result: Dict,
    resume_text: str = "",
    job_description: str = "",
    user_email: str = "",
) -> Optional[str]:
    serializable_result = _serializable_result(analysis_result)

    if not _use_supabase():
        inserted_id = str(uuid4())
        doc = {
            "id": inserted_id,
            "user_id": user_id,
            "user_email": user_email,
            "filename": filename,
            "ats_score": serializable_result.get("ats_score", 0),
            "keyword_match": serializable_result.get("keyword_match", 0),
            "missing_keywords": json.dumps(serializable_result.get("missing_keywords", [])),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "analysis_result": json.dumps(serializable_result),
            "resume_text": _safe_excerpt(resume_text, 20000),
            "job_description": _safe_excerpt(job_description, 12000),
        }
        try:
            _local_execute(
                """
                INSERT INTO analyses (
                    id, user_id, user_email, filename, ats_score, keyword_match,
                    missing_keywords, resume_text, job_description, analysis_result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc["id"],
                    doc["user_id"],
                    doc["user_email"],
                    doc["filename"],
                    doc["ats_score"],
                    doc["keyword_match"],
                    doc["missing_keywords"],
                    doc["resume_text"],
                    doc["job_description"],
                    doc["analysis_result"],
                    doc["created_at"],
                ),
            )
            logger.info(f"Saved local analysis for user {user_id}: {inserted_id}")
            return inserted_id
        except Exception as exc:
            logger.error(f"Failed to save local analysis: {exc}")
            return None

    headers = _get_headers()
    if not headers:
        return None

    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "filename": filename,
        "ats_score": serializable_result.get("ats_score", 0),
        "keyword_match": serializable_result.get("keyword_match", 0),
        "missing_keywords": serializable_result.get("missing_keywords", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_result": serializable_result,
        "resume_text": _safe_excerpt(resume_text, 20000),
        "job_description": _safe_excerpt(job_description, 12000),
    }

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/analyses"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=doc)
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                inserted_id = str(data[0].get("id"))
                logger.info(f"Saved analysis for user {user_id}: {inserted_id}")
                return inserted_id
            return None
    except Exception as exc:
        logger.error(f"Failed to save analysis to Supabase: {exc}")
        return None


async def log_login_event(
    user_id: str,
    email: str = "",
    provider: str = "",
    event_type: str = "login",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if not _use_supabase():
        inserted_id = str(uuid4())
        try:
            _local_execute(
                """
                INSERT INTO login_events (
                    id, user_id, email, provider, event_type, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inserted_id,
                    user_id,
                    email,
                    provider,
                    event_type,
                    json.dumps(metadata or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return inserted_id
        except Exception as exc:
            logger.error(f"Failed to save local login event: {exc}")
            return None

    headers = _get_headers()
    if not headers:
        return None

    doc = {
        "user_id": user_id,
        "email": email,
        "provider": provider,
        "event_type": event_type,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/login_events"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=doc)
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                return str(data[0].get("id"))
            return None
    except Exception as exc:
        logger.error(f"Failed to save login event to Supabase: {exc}")
        return None

async def get_user_history(user_id: str) -> List[Dict]:
    if not _use_supabase():
        try:
            cur = _local_execute(
                """
                SELECT * FROM analyses
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            results = []
            for row in cur.fetchall():
                doc = _row_to_dict(row)
                results.append({
                    "id": doc.get("id"),
                    "filename": doc.get("filename", "resume"),
                    "resume_name": doc.get("filename", "resume"),
                    "job_title": "Software Engineer",
                    "ats_score": doc.get("ats_score", 0),
                    "keyword_match": doc.get("keyword_match", 0),
                    "missing_keywords": json.loads(doc.get("missing_keywords", "[]") or "[]"),
                    "date": doc.get("created_at", ""),
                    "created_at": doc.get("created_at", ""),
                    "analysis_result": json.loads(doc.get("analysis_result", "{}") or "{}"),
                    "resume_text": doc.get("resume_text", ""),
                    "job_description": doc.get("job_description", ""),
                    "user_id": doc.get("user_id", ""),
                    "user_email": doc.get("user_email", ""),
                })
            return results
        except Exception as exc:
            logger.error(f"Failed to fetch local history: {exc}")
            return []

    headers = _get_headers()
    if not headers:
        return []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/analyses"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc"
                }
            )
            response.raise_for_status()
            docs = response.json()
            results = []
            for doc in docs:
                results.append({
                    "id": str(doc.get("id")),
                    "filename": doc.get("filename", "resume"),
                    "resume_name": doc.get("filename", "resume"),
                    "job_title": "Software Engineer",
                    "ats_score": doc.get("ats_score", 0),
                    "keyword_match": doc.get("keyword_match", 0),
                    "missing_keywords": doc.get("missing_keywords", []),
                    "date": doc.get("created_at", ""),
                    "created_at": doc.get("created_at", ""),
                    "analysis_result": doc.get("analysis_result", {}),
                    "resume_text": doc.get("resume_text", ""),
                    "job_description": doc.get("job_description", ""),
                    "user_id": doc.get("user_id", ""),
                    "user_email": doc.get("user_email", ""),
                })
            return results
    except Exception as exc:
        logger.error(f"Failed to fetch history from Supabase: {exc}")
        return []

async def get_all_history(limit: int = 100) -> List[Dict]:
    if not _use_supabase():
        try:
            cur = _local_execute(
                """
                SELECT * FROM analyses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            docs = []
            for row in cur.fetchall():
                doc = _row_to_dict(row)
                doc["missing_keywords"] = json.loads(doc.get("missing_keywords", "[]") or "[]")
                doc["analysis_result"] = json.loads(doc.get("analysis_result", "{}") or "{}")
                docs.append(doc)
            return docs
        except Exception as exc:
            logger.error(f"Failed to fetch local history: {exc}")
            return []

    headers = _get_headers()
    if not headers:
        return []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/analyses"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params={
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
            response.raise_for_status()
            docs = response.json()
            return docs if isinstance(docs, list) else []
    except Exception as exc:
        logger.error(f"Failed to fetch all history from Supabase: {exc}")
        return []

async def get_login_events(limit: int = 100) -> List[Dict]:
    if not _use_supabase():
        try:
            cur = _local_execute(
                """
                SELECT * FROM login_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            docs = []
            for row in cur.fetchall():
                doc = _row_to_dict(row)
                doc["metadata"] = json.loads(doc.get("metadata", "{}") or "{}")
                docs.append(doc)
            return docs
        except Exception as exc:
            logger.error(f"Failed to fetch local login events: {exc}")
            return []

    headers = _get_headers()
    if not headers:
        return []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/login_events"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params={
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
            response.raise_for_status()
            docs = response.json()
            return docs if isinstance(docs, list) else []
    except Exception as exc:
        logger.error(f"Failed to fetch login events from Supabase: {exc}")
        return []

async def delete_analysis(analysis_id: str, user_id: str) -> bool:
    if not _use_supabase():
        try:
            cur = _local_execute(
                "DELETE FROM analyses WHERE id = ? AND user_id = ?",
                (analysis_id, user_id),
            )
            return cur.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to delete local analysis {analysis_id}: {exc}")
            return False

    headers = _get_headers()
    if not headers:
        return False

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/analyses"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                url,
                headers=headers,
                params={
                    "id": f"eq.{analysis_id}",
                    "user_id": f"eq.{user_id}"
                }
            )
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.error(f"Failed to delete analysis {analysis_id}: {exc}")
        return False
