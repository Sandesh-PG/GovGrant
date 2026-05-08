"""
scraper.py — Multi-strategy web scraper for GovGrant Agent 2

Strategy:
  1. httpx (fast, async, handles static pages)
  2. Playwright fallback (headless Chromium, handles JS-heavy / anti-bot pages)

Exported:
  scrape_url(url) -> str | None   — raw HTML or None on total failure
  scrape_urls(urls) -> dict       — {url: html | None}
"""

import asyncio
import logging
import random
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── User-Agent pool (rotate to reduce bot detection) ─────────────────────────
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

_HTTPX_TIMEOUT = 20  # seconds
_PLAYWRIGHT_TIMEOUT = 30_000  # ms
_MAX_HTML_CHARS = 200_000  # trim very large pages before sending to Gemini


def _random_headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


# ── Strategy 1: httpx ─────────────────────────────────────────────────────────

async def _fetch_httpx(url: str) -> Optional[str]:
    """Async HTTP fetch. Returns HTML string or None."""
    try:
        async with httpx.AsyncClient(
            headers=_random_headers(),
            timeout=_HTTPX_TIMEOUT,
            follow_redirects=True,
            verify=False,  # some govt sites have cert issues
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type or "text/plain" in content_type:
                    html = resp.text
                    logger.info(f"[httpx] ✓ {url} ({len(html):,} chars)")
                    return html[:_MAX_HTML_CHARS]
                else:
                    logger.warning(f"[httpx] Non-HTML content-type at {url}: {content_type}")
                    return None
            else:
                logger.warning(f"[httpx] HTTP {resp.status_code} for {url}")
                return None
    except Exception as e:
        logger.warning(f"[httpx] Failed {url}: {e}")
        return None


# ── Strategy 2: Playwright ────────────────────────────────────────────────────

async def _fetch_playwright(url: str) -> Optional[str]:
    """
    Headless Chromium fetch via Playwright.
    Handles JS rendering, click-through cookie banners, lazy loading.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("[playwright] Not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                viewport={"width": 1280, "height": 800},
                locale="en-IN",
            )
            # Mask automation signals
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await context.new_page()

            try:
                await page.goto(url, timeout=_PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")
                # Wait for main content signals
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except PWTimeout:
                logger.warning(f"[playwright] Timeout waiting for {url}, grabbing partial HTML")

            html = await page.content()
            await browser.close()

            logger.info(f"[playwright] ✓ {url} ({len(html):,} chars)")
            return html[:_MAX_HTML_CHARS]

    except Exception as e:
        logger.error(f"[playwright] Failed {url}: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def scrape_url(url: str) -> Optional[str]:
    """
    Scrape a single URL.
    Tries httpx first; falls back to Playwright if httpx fails or
    returns suspiciously short HTML (likely a JS shell page).
    """
    html = await _fetch_httpx(url)

    # Heuristic: if page is a JS shell, httpx returns near-empty <body>
    if html is None or len(html.strip()) < 500:
        logger.info(f"[scraper] httpx gave thin/no HTML for {url}, trying Playwright…")
        html = await _fetch_playwright(url)

    return html


async def scrape_urls(urls: list[str], concurrency: int = 4) -> dict[str, Optional[str]]:
    """
    Scrape multiple URLs concurrently (bounded by `concurrency`).
    Returns {url: html_or_None}.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(url: str):
        async with semaphore:
            # Small jitter to avoid hammering same domain
            await asyncio.sleep(random.uniform(0.5, 2.0))
            return url, await scrape_url(url)

    results = await asyncio.gather(*[_bounded(u) for u in urls], return_exceptions=False)
    return dict(results)
