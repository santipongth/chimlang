"""hindcast — data cutoff enforcement + leak testing (TRUST-03, M1)"""

from trust.hindcast.filters import RetrievalFilter, extract_doc_date
from trust.hindcast.loader import HindcastDoc, HindcastEvent, load_event
from trust.hindcast.prompt import build_hindcast_system_prompt

__all__ = [
    "HindcastDoc",
    "HindcastEvent",
    "RetrievalFilter",
    "build_hindcast_system_prompt",
    "extract_doc_date",
    "load_event",
]
