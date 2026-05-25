#!/usr/bin/env python3
"""
Entry point for the Park4Night scraper.
Run from the project root: python scripts/scraper/run.py scrape
"""

import os
import sys

# Add scraper directory to path for direct execution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import main  # pyright: ignore[reportMissingImports]

if __name__ == "__main__":
    main()
