"""Views package for the Streamlit single-page app.

Submodules are imported lazily by the main app so one page does not force the
entire frontend to load at package import time.
"""

__all__ = ["landing", "scorer", "history", "resources"]
