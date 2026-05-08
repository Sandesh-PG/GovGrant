#!/bin/bash
# setup_agent2.sh — Install Agent 2 dependencies
# Run from govgrant-backend/ directory

set -e

echo "=== GovGrant Agent 2 Setup ==="
echo ""

echo "[1/3] Installing Python packages..."
pip install httpx==0.27.0 beautifulsoup4==4.12.3 lxml==5.2.1 playwright==1.44.0 chromadb==0.5.3

echo ""
echo "[2/3] Installing Playwright Chromium browser..."
playwright install chromium
playwright install-deps chromium  # system deps (Linux)

echo ""
echo "[3/3] Creating ChromaDB data directory..."
mkdir -p data/chroma_db
mkdir -p data/pdfs

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Agent 2 can now:"
echo "  ✓ Scrape govt portals with httpx"
echo "  ✓ Fall back to Playwright for JS-heavy pages"
echo "  ✓ Extract schemes via Gemini"
echo "  ✓ Index into ChromaDB"
echo "  ✓ Retrieve via RAG on subsequent sessions"
echo ""
echo "Start the backend: python -m uvicorn main:app --reload --port 8000"
