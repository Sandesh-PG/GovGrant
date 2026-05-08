"""
chroma_indexer.py — ChromaDB indexing for scraped scheme data

Indexes scraped schemes so future sessions can retrieve via RAG
without re-scraping (fast retrieval ~50ms vs scraping ~30s).

Collection: "govgrant_schemes"
Embedding:  Google text-embedding-004
Document:   scheme_name + criteria_text (what we embed)
Metadata:   all structured fields (for filtering)

Exported:
  index_schemes(schemes, api_key) -> int   (count indexed)
  rag_search(query, api_key, n_results)    -> list[dict]
  get_collection_stats() -> dict
"""

import hashlib
import logging
import os
from typing import Any

import chromadb
from chromadb.config import Settings
import httpx

logger = logging.getLogger(__name__)

# ── ChromaDB client (persistent) ─────────────────────────────────────────────

_CHROMA_PATH = os.environ.get("CHROMA_DB_PATH", "./data/chroma_db")
_COLLECTION_NAME = "govgrant_schemes"
_EMBED_MODEL = "text-embedding-004"
_EMBED_DIMENSION = 768


def _get_collection():
    """Get or create the ChromaDB collection."""
    client = chromadb.PersistentClient(
        path=_CHROMA_PATH,
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ── Google Embeddings ─────────────────────────────────────────────────────────

async def _embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """
    Embed a batch of texts using Google text-embedding-004.
    Returns list of embedding vectors.
    """
    embeddings = []

    # Google embeddings API accepts up to 100 texts per batch
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {
            "model": f"models/{_EMBED_MODEL}",
            "content": {"parts": [{"text": t} for t in batch]},
        }

        # Use batchEmbedContents for multiple texts
        batch_payload = {
            "requests": [
                {
                    "model": f"models/{_EMBED_MODEL}",
                    "content": {"parts": [{"text": t}]},
                }
                for t in batch
            ]
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{_EMBED_MODEL}:batchEmbedContents",
                params={"key": api_key},
                json=batch_payload,
            )
            resp.raise_for_status()
            data = resp.json()

        for emb in data.get("embeddings", []):
            embeddings.append(emb["values"])

    return embeddings


# ── Indexing ──────────────────────────────────────────────────────────────────

def _scheme_to_document(scheme: dict) -> str:
    """Create the text document to embed from a scheme dict."""
    parts = []
    if name := scheme.get("scheme_name"):
        parts.append(f"Scheme: {name}")
    if criteria := scheme.get("criteria_text"):
        parts.append(f"Eligibility: {criteria}")
    if amount := scheme.get("grant_amount"):
        parts.append(f"Grant Amount: {amount}")
    if types := scheme.get("eligible_types"):
        if isinstance(types, list):
            parts.append(f"Eligible Entity Types: {', '.join(types)}")
        elif isinstance(types, str):
            parts.append(f"Eligible Entity Types: {types}")
    return "\n".join(parts)


def _scheme_id(scheme: dict) -> str:
    """Stable, unique ID for a scheme based on its name."""
    name = (scheme.get("scheme_name") or "unknown").strip().lower()
    return hashlib.md5(name.encode()).hexdigest()


async def index_schemes(schemes: list[dict[str, Any]], api_key: str) -> int:
    """
    Index a list of scraped schemes into ChromaDB.
    Skips schemes already indexed (upsert by ID).
    
    Returns: count of newly indexed schemes
    """
    if not schemes:
        return 0

    collection = _get_collection()

    # Build documents and IDs
    documents = [_scheme_to_document(s) for s in schemes]
    ids = [_scheme_id(s) for s in schemes]

    # Build metadata (ChromaDB requires flat dicts with str/int/float/bool values)
    metadatas = []
    for s in schemes:
        eligible = s.get("eligible_types", [])
        if isinstance(eligible, list):
            eligible_str = ",".join(eligible)
        else:
            eligible_str = str(eligible or "")

        metadatas.append({
            "scheme_name": str(s.get("scheme_name") or ""),
            "source_url": str(s.get("portal_url") or s.get("source_url") or ""),
            "grant_amount": str(s.get("grant_amount") or ""),
            "deadline": str(s.get("deadline") or ""),
            "eligible_types": eligible_str,
            "max_revenue_inr": int(s.get("max_revenue_inr") or 0),
            "source_type": str(s.get("source_type") or "live"),
        })

    # Get embeddings
    try:
        embeddings = await _embed_texts(documents, api_key)
    except Exception as e:
        logger.error(f"[chroma] Embedding failed: {e}. Indexing without embeddings.")
        embeddings = None

    # Upsert into ChromaDB
    try:
        if embeddings:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        else:
            # ChromaDB will use its default embedding if no embeddings provided
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

        count = len(ids)
        logger.info(f"[chroma] Indexed {count} schemes into '{_COLLECTION_NAME}'")
        return count

    except Exception as e:
        logger.error(f"[chroma] Upsert failed: {e}")
        return 0


# ── RAG Search ────────────────────────────────────────────────────────────────

async def rag_search(
    query: str,
    api_key: str,
    n_results: int = 15,
) -> list[dict]:
    """
    Search ChromaDB for schemes relevant to a query.
    Returns list of metadata dicts for matched schemes.
    
    Usage:
        query = "food processing MSME Maharashtra startup grant"
        results = await rag_search(query, api_key)
    """
    collection = _get_collection()

    if collection.count() == 0:
        logger.info("[chroma] Collection is empty, RAG returning []")
        return []

    try:
        # Embed the query
        query_embeddings = await _embed_texts([query], api_key)
        query_embedding = query_embeddings[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        schemes = []
        for i, metadata in enumerate(results["metadatas"][0]):
            scheme = dict(metadata)
            scheme["criteria_text"] = results["documents"][0][i]
            scheme["rag_score"] = round(1.0 - results["distances"][0][i], 3)
            schemes.append(scheme)

        logger.info(f"[chroma] RAG returned {len(schemes)} schemes for query: {query[:60]}")
        return schemes

    except Exception as e:
        logger.error(f"[chroma] RAG search failed: {e}")
        return []


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_collection_stats() -> dict:
    """Return stats about the ChromaDB collection."""
    try:
        collection = _get_collection()
        return {
            "collection": _COLLECTION_NAME,
            "total_schemes": collection.count(),
            "path": _CHROMA_PATH,
        }
    except Exception as e:
        return {"error": str(e)}
