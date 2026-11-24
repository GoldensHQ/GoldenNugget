"""App version constants shared by the backend and the GUI.

Historically these lived in ``src/gui/version.py``; they moved here so the
backend (hotload, crash handling, logging, update checks) never depends on the
GUI package. ``src/gui/version.py`` re-exports them for the GUI side.
"""

App_Version = "9.7.10"
App_Build = 0

# Top-level key used by files GoldenNugget writes to record which build wrote
# them (settings, preset exports). This is writer metadata, not a user
# preference and not a file-format version.
GNUGGET_VERSION = "GNUGGET_VERSION"
