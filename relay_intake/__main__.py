"""``python3 -m relay_intake`` — the conformance suite's entry point."""

import sys

from relay_intake.conformance import main

if __name__ == "__main__":
    sys.exit(main())
