"""
Scheme PDF Ingestion Script — One-time ChromaDB loader.

Usage:
    python scripts/ingest_schemes.py --pdf-dir ./data/scheme_pdfs

This script:
1. Reads all PDFs in the specified directory
2. Extracts text and chunks into ~500-token segments
3. Extracts metadata from filename convention: <scheme_id>__<ministry>.pdf
4. Embeds chunks using Google text-embedding-004
5. Stores in ChromaDB with rich metadata for filtered retrieval
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

# PDF parsing — try pdfplumber then pypdf as fallback
try:
    import pdfplumber
    PDF_BACKEND = "pdfplumber"
except ImportError:
    try:
        import pypdf
        PDF_BACKEND = "pypdf"
    except ImportError:
        print("ERROR: Install pdfplumber or pypdf: pip install pdfplumber")
        sys.exit(1)

# ─── Constants ─────────────────────────────────────────────────────────────────

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
COLLECTION_NAME = "govgrant_schemes"
CHUNK_SIZE = 500      # tokens (approx chars / 4)
CHUNK_OVERLAP = 50

# Known sectors for metadata tagging
SECTOR_KEYWORDS = {
    "agriculture": ["agri", "farm", "crop", "horticulture", "fishery", "animal"],
    "manufacturing": ["manufactur", "industrial", "factory", "production"],
    "it_tech": ["technology", "software", "it ", "digital", "startup", "innovation"],
    "healthcare": ["health", "medical", "pharma", "hospital"],
    "food_processing": ["food", "processing", "packag", "beverage"],
    "textile": ["textile", "garment", "weaving", "handloom", "apparel"],
    "renewable_energy": ["solar", "wind", "renewable", "clean energy", "green"],
    "msme": ["msme", "small enterprise", "medium enterprise", "udyam"],
}

ENTITY_KEYWORDS = {
    "startup": ["startup", "new venture", "incorporated after"],
    "msme": ["msme", "micro", "small", "medium enterprise"],
    "proprietorship": ["proprietorship", "sole proprietor"],
    "women": ["women", "mahila", "female entrepreneur"],
    "sc_st": ["sc/st", "scheduled caste", "scheduled tribe", "dalit"],
}


# ─── Text extraction ───────────────────────────────────────────────────────────

def extract_text_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)


def extract_text_pypdf(pdf_path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join(
        page.extract_text() or "" for page in reader.pages
    )


def extract_text(pdf_path: Path) -> str:
    if PDF_BACKEND == "pdfplumber":
        return extract_text_pdfplumber(pdf_path)
    return extract_text_pypdf(pdf_path)


# ─── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks of ~chunk_size tokens."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return [c for c in chunks if len(c.strip()) > 50]


# ─── Metadata extraction ───────────────────────────────────────────────────────

def infer_metadata_from_text(text: str, filename: str) -> Dict[str, Any]:
    """Infer scheme metadata from PDF text and filename."""
    text_lower = text.lower()

    # Infer sectors
    sectors = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            sectors.append(sector)

    # Revenue cap detection
    revenue_match = re.search(
        r"turnover[^\d]*(?:not exceeding|up to|less than|below)[^\d]*"
        r"(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(lakh|crore|cr|l)?",
        text_lower,
    )
    max_revenue = None
    if revenue_match:
        amount = float(revenue_match.group(1).replace(",", ""))
        unit = revenue_match.group(2) or ""
        if "crore" in unit or "cr" in unit:
            max_revenue = amount * 1e7
        elif "lakh" in unit or unit == "l":
            max_revenue = amount * 1e5

    # Grant amount detection
    grant_match = re.search(
        r"(?:grant|subsidy|loan)[^\d]*(?:up to|maximum|max)[^\d]*"
        r"(?:rs\.?|inr|₹)?\s*([\d,]+)\s*(lakh|crore|cr|l)?",
        text_lower,
    )
    grant_amount = None
    if grant_match:
        amount = float(grant_match.group(1).replace(",", ""))
        unit = grant_match.group(2) or ""
        if "crore" in unit or "cr" in unit:
            grant_amount = amount * 1e7
        elif "lakh" in unit or unit == "l":
            grant_amount = amount * 1e5

    # Entity types
    entity_types = []
    if any(kw in text_lower for kw in ENTITY_KEYWORDS["startup"]):
        entity_types.append("startup")
    if any(kw in text_lower for kw in ENTITY_KEYWORDS["msme"]):
        entity_types.extend(["msme", "proprietorship", "partnership", "private_limited"])
    if not entity_types:
        entity_types = ["msme", "startup", "private_limited", "proprietorship"]

    # Parse filename: scheme_id__ministry.pdf
    stem = Path(filename).stem
    parts = stem.split("__")
    scheme_id = parts[0].lower().replace(" ", "_")
    ministry = parts[1].replace("_", " ").title() if len(parts) > 1 else "Government of India"

    return {
        "scheme_id": scheme_id,
        "name": scheme_id.replace("_", " ").title(),
        "ministry": ministry,
        "portal_url": f"https://www.india.gov.in/search?query={scheme_id}",
        "description": text[:200].replace("\n", " "),
        "eligible_sectors": sectors or ["all"],
        "eligible_entity_types": entity_types,
        "eligible_states": [],  # empty = pan-India
        "max_revenue_inr": max_revenue,
        "grant_amount_inr": grant_amount,
        "source": "rag",
    }


# ─── Ingestion ─────────────────────────────────────────────────────────────────

def ingest_pdfs(pdf_dir: Path, metadata_json: Optional[Path] = None) -> None:
    """Main ingestion function."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY environment variable not set")
        sys.exit(1)

    # Load optional metadata override JSON
    metadata_overrides: Dict[str, Dict] = {}
    if metadata_json and metadata_json.exists():
        with open(metadata_json) as f:
            metadata_overrides = json.load(f)
        print(f"Loaded metadata overrides for {len(metadata_overrides)} schemes")

    # Init ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=api_key,
        model_name="models/text-embedding-004",
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {pdf_dir}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDFs — ingesting into ChromaDB at {CHROMA_PATH}")

    total_chunks = 0
    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name} ...", end="", flush=True)

        # Extract text
        try:
            text = extract_text(pdf_path)
        except Exception as e:
            print(f" FAILED ({e})")
            continue

        if not text.strip():
            print(" SKIPPED (empty)")
            continue

        # Build metadata
        base_meta = infer_metadata_from_text(text, pdf_path.name)
        if pdf_path.stem in metadata_overrides:
            base_meta.update(metadata_overrides[pdf_path.stem])

        # Chunk text
        chunks = chunk_text(text)

        # Prepare ChromaDB documents
        ids = [f"{base_meta['scheme_id']}__chunk_{i}" for i in range(len(chunks))]
        metadatas = []
        for i, chunk in enumerate(chunks):
            meta = {**base_meta, "chunk_index": i, "total_chunks": len(chunks)}
            # ChromaDB requires scalar values — serialize lists
            for key in ["eligible_sectors", "eligible_entity_types", "eligible_states"]:
                if isinstance(meta.get(key), list):
                    meta[key] = json.dumps(meta[key])
            # Remove None values
            meta = {k: v for k, v in meta.items() if v is not None}
            metadatas.append(meta)

        # Upsert in batches of 50
        batch_size = 50
        for start in range(0, len(chunks), batch_size):
            collection.upsert(
                ids=ids[start : start + batch_size],
                documents=chunks[start : start + batch_size],
                metadatas=metadatas[start : start + batch_size],
            )

        total_chunks += len(chunks)
        print(f" OK ({len(chunks)} chunks)")

    print(f"\n✅ Ingestion complete: {total_chunks} total chunks in ChromaDB")
    print(f"   Collection: '{COLLECTION_NAME}' at {CHROMA_PATH}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest government scheme PDFs into ChromaDB for GovGrant RAG"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("./data/scheme_pdfs"),
        help="Directory containing scheme PDF files",
    )
    parser.add_argument(
        "--metadata-json",
        type=Path,
        default=None,
        help="Optional JSON file with metadata overrides per scheme_id",
    )
    parser.add_argument(
        "--chroma-path",
        type=str,
        default=None,
        help="Override ChromaDB path (default: $CHROMA_DB_PATH or ./data/chroma_db)",
    )

    args = parser.parse_args()

    if args.chroma_path:
        os.environ["CHROMA_DB_PATH"] = args.chroma_path
        CHROMA_PATH = args.chroma_path

    ingest_pdfs(args.pdf_dir, args.metadata_json)
