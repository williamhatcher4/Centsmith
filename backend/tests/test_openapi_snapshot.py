"""OpenAPI snapshot drift guard (plan item P5.7).

``frontend/src/types.ts`` and ``frontend/src/test/handlers.ts`` are hand-maintained
mirrors of the backend Pydantic schemas. A breaking shape change — the Phase-2
pagination switch to ``{items, ...}`` is the canonical example — otherwise
produces no signal at the boundary; it is caught only if an e2e spec happens to
cross the changed endpoint.

This test pins the API contract. **A snapshot diff in a change is the cue to
update ``types.ts``, ``test/handlers.ts``, and any affected e2e expectations in
the SAME commit** — the snapshot diff and the frontend updates should always
travel together.

To regenerate after an intentional API change, run with ``UPDATE_OPENAPI_SNAPSHOT=1``:

    # bash
    UPDATE_OPENAPI_SNAPSHOT=1 python -m pytest tests/test_openapi_snapshot.py
    # PowerShell
    $env:UPDATE_OPENAPI_SNAPSHOT=1; python -m pytest tests/test_openapi_snapshot.py

The ``info`` block (release ``version`` + ``title``) is stripped before
comparison so the snapshot does not churn on every release.
"""

import difflib
import json
import os
from pathlib import Path

from app.main import app

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi.json"

# The literal command a developer should run to refresh the snapshot, embedded in
# both the regeneration notice and the failure message.
REGEN_COMMAND = "UPDATE_OPENAPI_SNAPSHOT=1 python -m pytest tests/test_openapi_snapshot.py"


def _normalized_spec() -> str:
    """``app.openapi()`` minus the churning ``info`` block, stably serialized."""
    spec = {k: v for k, v in app.openapi().items() if k != "info"}
    return json.dumps(spec, sort_keys=True, indent=2) + "\n"


def test_openapi_snapshot_matches():
    current = _normalized_spec()

    if os.environ.get("UPDATE_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")
        print(f"\nUpdated OpenAPI snapshot at {SNAPSHOT_PATH}")
        return

    assert SNAPSHOT_PATH.exists(), (
        f"OpenAPI snapshot is missing. Generate it with:\n    {REGEN_COMMAND}"
    )
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if current != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                current.splitlines(keepends=True),
                fromfile="snapshots/openapi.json (committed)",
                tofile="app.openapi() (current)",
            )
        )
        raise AssertionError(
            "OpenAPI schema drifted from the committed snapshot.\n"
            "If this change is intentional, update frontend/src/types.ts, "
            "frontend/src/test/handlers.ts, and any affected e2e specs in the "
            "SAME commit, then regenerate the snapshot:\n"
            f"    {REGEN_COMMAND}\n\n"
            f"{diff}"
        )
