"""Compatibility shim — the statement parsers now live in the
``app.services.statement_parsing`` package (plan item P4.2).

``__all__`` in the package includes the underscore helpers the tests import,
so this star-import re-exports the full historical surface of this module.
"""
from app.services.statement_parsing import *  # noqa: F401,F403
