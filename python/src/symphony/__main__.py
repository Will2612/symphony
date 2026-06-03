"""`python -m symphony …` entrypoint.

Delegates to `symphony.cli.main`. Kept intentionally thin so the
console-script entry point (`symphony = "symphony.cli:main"`,
declared in `pyproject.toml`) and the `python -m` invocation stay
in lock-step — both go through the same `main()` function.
"""

from __future__ import annotations

import sys

from symphony.cli import main

__all__ = ["main"]

if __name__ == "__main__":
    sys.exit(main())
