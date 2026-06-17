"""Blog pond — upcoming scheduled posts from WordPress."""
import logging
import os
import httpx

log = logging.getLogger(__name__)
POND_NAME = "blog"


async def run() -> dict:
    """Fetch upcoming scheduled WordPress posts."""
    url = os.environ.get("WORDPRESS_URL", "")
    user = os.environ.get("WORDPRESS_USER", "")
    password = os.environ.get("WORDPRESS_APP_PASSWORD", "")

    if not all([url, user, password]):
        return {"pond": POND_NAME, "error": "WordPress not configured",
                "summary": "✍️ Blog: not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{url.rstrip('/')}/wp-json/wp/v2/posts",
                params={"status": "future", "per_page": 5, "orderby": "date", "order": "asc"},
                auth=(user, password),
            )
            response.raise_for_status()
            posts = response.json()

        if not posts:
            return {"pond": POND_NAME, "posts": [], "summary": "✍️ Blog: nothing scheduled", "error": None}

        lines = ["✍️ <b>Blog</b> — Upcoming"]
        for post in posts[:5]:
            date_str = post.get("date", "")[:10]
            title = post.get("title", {}).get("rendered", "(untitled)")
            lines.append(f"   • {date_str}: {title}")

        return {
            "pond": POND_NAME,
            "posts": posts,
            "summary": "\n".join(lines),
            "error": None,
        }

    except Exception as e:
        log.error("Blog pond error: %s", e)
        return {"pond": POND_NAME, "error": str(e), "summary": f"✍️ Blog: unavailable"}
