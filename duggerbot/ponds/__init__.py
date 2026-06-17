"""Pond interface — async functions that collect and return structured data.

Each pond:
  - Is an async function named `run()`
  - Returns a dict with at minimum {"pond": str, "summary": str}
  - Never raises — catches all exceptions and returns {"pond": name, "error": str}
  - Is self-contained — no shared state between ponds
"""
from typing import Protocol


class Pond(Protocol):
    async def __call__(self) -> dict:
        """Run the pond and return structured data."""
        ...
