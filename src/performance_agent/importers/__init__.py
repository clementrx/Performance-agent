"""Activity-file import: parse .fit/.tcx/.gpx/CSV into proposed sessions.

These modules do I/O and use third-party parsers and datetime (unlike the pure
engine). Parsing only PROPOSES a session for the athlete to confirm — nothing is
written here; logging still goes through the memory store after confirmation.
"""

from performance_agent.importers.activity import (
    ActivityImportError,
    HrvReading,
    ParsedActivity,
    parse_activity_file,
)

__all__ = [
    "ActivityImportError",
    "HrvReading",
    "ParsedActivity",
    "parse_activity_file",
]
