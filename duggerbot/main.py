"""DuggerBot — entry point.

Run via:  uv run python -m duggerbot.main
NSSM:     uv run python -m duggerbot.main (in AppDirectory = repo root)
"""

import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def _configure_logging() -> None:
    """Configure root logger with console and file handlers.

    StreamHandler: captured by NSSM as stdout/stderr.
    FileHandler:   secondary audit trail in logs/duggerbot.log,
                   survives NSSM log rotation.
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "duggerbot.log"),
        ],
    )


def main() -> None:
    # override=False: system env vars (e.g. set by NSSM) win over .env.local
    load_dotenv(".env.local", override=False)
    _configure_logging()

    log = logging.getLogger(__name__)
    port = int(os.environ.get("MCP_PORT", "8001"))
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    instance = os.environ.get("INSTANCE_ROLE", "unknown")

    log.info("TOBOR starting — instance=%s host=%s port=%s", instance, host, port)

    uvicorn.run(
        "duggerbot.mcp.server:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
