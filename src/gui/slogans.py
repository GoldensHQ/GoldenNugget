"""Per-launch random brand slogans.

Picked ONCE per process (:func:`launch_slogan` returns one of ``SLOGANS`` for
the whole run) so widgets created later — dock rebuilts, panel rebuilds — all
show the same launch's slogan; the liquid dock's ``LiquidBrand`` renders it.
"""
import random

SLOGANS = (
    "works on my device",
    "posterboard my beloved",
    "trust the process",
    "sparse restore enjoyer",
    "certified nugget moment",
    "Phase 5 speedrun",
    "no refunds!",
    "free at point of use",
    "MBErrorDomain 205 club",
    "tested on one device",
    "siri, don't testify",
    "hi",
)

_LAUNCH_SLOGAN = random.choice(SLOGANS)


def launch_slogan() -> str:
    """This launch's slogan — the same string for every caller this session."""
    return _LAUNCH_SLOGAN
