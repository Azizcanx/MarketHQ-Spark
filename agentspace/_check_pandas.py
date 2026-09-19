#!/usr/bin/env python3
import sys
try:
    import pandas
    print("pandas OK:", pandas.__version__)
except ImportError:
    print("pandas MISSING")
    sys.exit(1)
