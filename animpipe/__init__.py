"""Deprecated alias — the toolkit is now `flumen` (the app was renamed from its
Legami-era branding). `python -m animpipe …` still works during the transition;
switch scripts to `python -m flumen …`."""

from flumen import __version__  # noqa: F401 — keep the old version probe working
