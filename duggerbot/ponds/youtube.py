"""YouTube pond — channel analytics and top video for last 7 days."""
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)
POND_NAME = "youtube"


async def run() -> dict:
    """Fetch YouTube channel analytics and top video."""
    try:
        from duggerbot.ponds.google_auth import get_credentials
        from googleapiclient.discovery import build

        creds = get_credentials()
        if creds is None:
            return {"pond": POND_NAME, "error": "No credentials", "summary": "📺 YouTube: credentials not configured"}

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=7)
        start_str = start.isoformat()
        end_str = end.isoformat()

        # Analytics: views and subscribers
        analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        report = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_str,
            endDate=end_str,
            metrics="views,subscribersGained,subscribersLost",
        ).execute()

        rows = report.get("rows", [[0, 0, 0]])
        row = rows[0] if rows else [0, 0, 0]
        views, subs_gained, subs_lost = int(row[0]), int(row[1]), int(row[2])
        sub_delta = subs_gained - subs_lost

        # Top video by views
        top_video_report = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_str,
            endDate=end_str,
            dimensions="video",
            metrics="views",
            sort="-views",
            maxResults=1,
        ).execute()

        top_title = "—"
        top_views = 0
        top_rows = top_video_report.get("rows", [])
        if top_rows:
            top_video_id = top_rows[0][0]
            top_views = int(top_rows[0][1])
            data_client = build("youtube", "v3", credentials=creds, cache_discovery=False)
            video_resp = data_client.videos().list(part="snippet", id=top_video_id).execute()
            items = video_resp.get("items", [])
            if items:
                top_title = items[0]["snippet"]["title"]

        sub_str = f"+{sub_delta}" if sub_delta >= 0 else str(sub_delta)
        summary = (
            f"📺 <b>YouTube</b> (last 7 days)\n"
            f"   Views: {views:,} | Subs: {sub_str}\n"
            f"   Top: {top_title} ({top_views:,})"
        )

        return {
            "pond": POND_NAME,
            "views": views,
            "sub_delta": sub_delta,
            "top_title": top_title,
            "top_views": top_views,
            "summary": summary,
            "error": None,
        }

    except Exception as e:
        log.error("YouTube pond error: %s", e)
        return {"pond": POND_NAME, "error": str(e), "summary": f"📺 YouTube: unavailable ({e})"}
