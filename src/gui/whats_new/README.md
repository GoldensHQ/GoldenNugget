# What's New media

Drop screenshots/GIFs here to show them in the "What's New" window of one
release. Name every file `<version>-<anything>.<ext>` — e.g.
`10.0-banner.png`, `10.0-cache.gif` — using the same version key as
`WHATS_NEW` in `../dialogs/whats_new.py`.

- Supported: PNG, JPG, WEBP, SVG (static) and GIF (animated).
- Files are shown under the bullet list, in file-name order, scaled to fit
  the card (max 440×220); nothing is needed in code — a new file shows up
  automatically for its version.
- The folder ships with every packaged version (`compile.py` add-data).
