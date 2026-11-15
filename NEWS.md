# GoldenNugget Release News

Each section describes one release, newest first. Ship this file with every
packaged version (bundled at the app root by `compile.py`) and keep the
current release's bullets in sync with `WHATS_NEW` in
`src/gui/dialogs/whats_new.py`, which drives the "What's New" window shown
after an update.

## 10.0

Upgrading from 9.7.7 — this is what you get:

### Highlights

- **iOS 27 support is no longer experimental.** The whole apply flow works
  on iOS 27, and applies got a new shape by default: the device is no longer
  rebooted into the "safe state recovery" wipe in the middle of an apply.
  One session, no 20-minute wait for the device to come back, no forced
  re-setup — tweaks and your data land in the same pass.
- **Faster applies with the backup cache (experimental).** A per-device
  master backup is kept between applies and refreshed incrementally: repeat
  applies only upload what actually changed on the phone. Photos are synced
  separately and only the new/changed ones move. You can turn this off in
  Settings → Backup ("Use Fast Backup Cache").
- **Safer applies.** The apply now refuses to start unless your protective
  backup is verified complete, and keeps the previous backup until the
  restore finishes. The AFC photo store is tracked with a completeness
  marker, so an interrupted photo pull can never quietly become "the only
  copy of your library".
- **GoldenNugget Mobile Helper grew a full sideload engine**: sign in with
  your Apple ID (2FA supported, free accounts included) to re-sign and
  install IPAs, and deliver the RemotePairing pairing record the iOS 26.4+
  helper app needs — no PIN, no on-device Trust dialog.
- **The interface got a new coat of paint**: one dark palette with 8 accent
  color choices (Settings → Appearance), animated loading screens the first
  time you open a page, centered card headers, bigger navigation controls,
  and the gold dock icon shimmer is back.

### Fixes since 9.7.7

- Windows: the app no longer crashes with an empty window / "Entry Point
  Not Found" when an unrelated OpenSSL is present on your PATH (VPN/CLI
  installs do this) — TLS is pinned to the system Schannel.
- Windows: encrypted-backup applies no longer fail with a hidden temp-file
  permission error while pruning the manifest.
- Linux: packaged releases start again on older distros (Ubuntu 22.04,
  Debian 12, RHEL 9 — glibc 2.34); the 10.0 pipeline builds inside a
  matching toolchain so a fresh release cannot demand a newer glibc than
  your system has.
- PosterBoard: solid-color wallpapers inject into the correct layer, so
  they actually show up (issue #90); a saved wallpaper database heals
  itself instead of demanding a re-fetch.
- A `ScreenTimeAgent` reset no longer aborts every apply; battery-only
  applies no longer touch the PosterBoard database path.
- Reset: plists are rewritten as valid empty files, so SpringBoard can no
  longer boot-loop after a reset on iOS 26.2+; managed-preference mirrors
  are cleared too (the Dynamic Island stays gone after a reset).
- Managed preferences that are unreadable on the device no longer abort
  the whole apply — they degrade to whole-file delivery (issue #85).
- Video-loop wallpaper exports stay inside the device's decoded-pixel
  budget, so large loops actually play (issue #86).
- Carrier name override with a blank name now hides the carrier label
  instead of showing it empty (issue #83).
- The one-time data-folder move no longer stalls on folders over 2 GiB;
  a dismissing it is remembered until the plan changes.
- Crash reports open correctly when a crash happens off the main thread
  (no more instant abort inside the crash dialog itself).
- New daemon/preference controls were added (opt-in), and reviewed
  inactive daemon controls are grouped under Risky Tweaks.

### Housekeeping

- The legacy Designer UI stack is gone; the UI library now lives in the
  `awesomeui` submodule.
- This file (`NEWS.md`) ships with every release, and a "What's New"
  window opens after each update.

## 9.7.7

- Bug fixes and improvements.
