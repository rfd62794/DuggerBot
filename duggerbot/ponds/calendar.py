"""Calendar pond — today's events and upcoming 7 days."""
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)
POND_NAME = "calendar"


async def run() -> dict:
    """Fetch today's Google Calendar events."""
    try:
        from duggerbot.ponds.google_auth import get_credentials
        from googleapiclient.discovery import build

        creds = get_credentials()
        if creds is None:
            return {"pond": POND_NAME, "error": "No credentials", "summary": "📅 Calendar: not configured"}

        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])

        if not events:
            summary = "📅 <b>Calendar</b> — Nothing scheduled this week"
            return {"pond": POND_NAME, "events": [], "summary": summary, "error": None}

        today = now.date()
        lines = ["📅 <b>Calendar</b>"]
        for event in events[:5]:
            start_info = event.get("start", {})
            start_str = start_info.get("dateTime") or start_info.get("date", "")
            title = event.get("summary", "(no title)")
            try:
                if "T" in start_str:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    time_label = dt.astimezone().strftime("%b %d %I:%M %p").lstrip("0")
                else:
                    time_label = start_str
            except Exception:
                time_label = start_str
            lines.append(f"   • {time_label} — {title}")

        return {
            "pond": POND_NAME,
            "events": events,
            "summary": "\n".join(lines),
            "error": None,
        }

    except Exception as e:
        log.error("Calendar pond error: %s", e)
        return {"pond": POND_NAME, "error": str(e), "summary": f"📅 Calendar: unavailable"}
