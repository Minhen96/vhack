"""
Shared Coverage Grid
====================
Tracks which map areas have already been scanned — persists across drone
disconnects and reconnects. Stored in the backend so any drone can query
what's covered before starting a search.

Grid bucket approach: the map is divided into BUCKET_SIZE × BUCKET_SIZE cells.
Both passive fly-over scans and explicit thermal_scan waypoints mark coverage.
Passive scan fires at every movement cell (step=1) with radius=8 fov=360,
so the full flight path is covered — no gaps between snake rows.

A snake-pattern waypoint is skipped if its bucket is already marked, so a new
drone assigned to the same zone picks up only the uncovered remainder.
"""

BUCKET_SIZE = 8  # matches SCAN_RADIUS_DEFAULT — each bucket ~= one scan circle


class CoverageGrid:
    def __init__(self) -> None:
        self._buckets: set[tuple[int, int]] = set()

    def mark(self, x: int, y: int) -> None:
        """Mark the bucket containing (x, y) as scanned."""
        self._buckets.add((x // BUCKET_SIZE, y // BUCKET_SIZE))

    def is_covered(self, x: int, y: int) -> bool:
        """Return True if (x, y) falls in an already-scanned bucket."""
        return (x // BUCKET_SIZE, y // BUCKET_SIZE) in self._buckets

    def get_buckets(self) -> list[list[int]]:
        """Return all covered buckets as [[gx, gy], ...] for JSON serialisation."""
        return [[gx, gy] for gx, gy in self._buckets]

    def reset(self) -> None:
        """Clear all coverage — call at the start of a new mission."""
        self._buckets.clear()


# Singleton shared across all requests in the backend process
coverage = CoverageGrid()