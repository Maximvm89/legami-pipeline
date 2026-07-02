"""`python -m animpipe` — deprecated alias for `python -m flumen`."""

import sys

from flumen.cli import main

print("note: 'animpipe' is now 'flumen'; this alias will go away.", file=sys.stderr)
sys.exit(main())
