"""Dev.to pond — published article stats."""
import logging
import os
import httpx

log = logging.getLogger(__name__)
POND_NAME = "devto"


async def run() -> dict:
    """Fetch Dev.to article statistics."""
    api_key = os.environ.get("DEVTO_API_KEY", "")
    if not api_key:
        return {"pond": POND_NAME, "error": "DEVTO_API_KEY not set",
                "summary": "📊 Dev.to: not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://dev.to/api/articles/me/published",
                headers={"api-key": api_key},
                params={"per_page": 10},
            )
            response.raise_for_status()
            articles = response.json()

        total_reads = sum(a.get("page_views_count", 0) for a in articles)
        total_reactions = sum(a.get("positive_reactions_count", 0) for a in articles)

        summary = (
            f"📊 <b>Dev.to</b>\n"
            f"   Articles: {len(articles)} | "
            f"Reads: {total_reads:,} | "
            f"Reactions: {total_reactions}"
        )

        return {
            "pond": POND_NAME,
            "article_count": len(articles),
            "total_reads": total_reads,
            "total_reactions": total_reactions,
            "summary": summary,
            "error": None,
        }

    except Exception as e:
        log.error("Dev.to pond error: %s", e)
        return {"pond": POND_NAME, "error": str(e), "summary": f"📊 Dev.to: unavailable"}
