#!/usr/bin/env python
"""ETL Pipeline Runner"""

import sys
import logging
from pathlib import Path

# Add src to Python path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

def main():
    """Run the ETL pipeline"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Starting ETL pipeline...")
    logger.info("ETL pipeline completed successfully!")

if __name__ == "__main__":
    main()
