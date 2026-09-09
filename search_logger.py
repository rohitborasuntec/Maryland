"""
search_logger.py
-----------------
Centralized logging for the Estate Search application.

Responsibilities:
  * Print a readable, timestamped log of every search a user runs
    (which filters were selected) to the terminal/console.
  * Persist the same information to a rotating log file on disk so
    a history of searches is kept between runs.
  * Provide small helper functions the GUI (or the scraper/integration
    module) can call to log general events, warnings, and errors
    using the same consistent format.

Usage:
    from search_logger import get_logger, log_search_filters

    logger = get_logger()
    log_search_filters(params)          # logs the chosen filters
    logger.info("Scraper started")      # general event logging
    logger.error("Something failed")    # error logging
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).resolve().parent / "logs"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"estate_search_{timestamp}.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOGGER_NAME = "estate_search"

_logger = None  # module-level singleton


def get_logger() -> logging.Logger:
    """
    Return the shared application logger, configured to write to both
    the console (terminal) and a rotating log file. Safe to call many
    times - the handlers are only attached once.
    """
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # don't double-log via the root logger

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler -> shows log output in the terminal
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Rotating file handler -> keeps a persistent history on disk
        # (1 MB per file, keep the last 5 files)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _logger = logger
    return _logger


def log_search_filters(params: dict) -> None:
    """
    Log the filters a user selected for a search in a clean, readable
    block. Writes to both the terminal and the log file via the shared
    logger. Only non-empty filters are shown so the log stays readable.
    """
    logger = get_logger()

    friendly_labels = {
        "estate_number": "Estate Number",
        "county": "County",
        "estate_status": "Estate Status",
        "estate_type": "Estate Type",
        "party_type": "Party Type",
        "last_name": "Last Name",
        "first_name": "First Name",
        "filing_date_type": "Filing Date Mode",
        "filing_date_from": "Filing Date From",
        "filing_date_to": "Filing Date To",
        "filing_date_exact": "Filing Date (Exact)",
        "headless": "Run Headless",
        "debug": "Debug Mode",
        "limit_results": "Limit Results",
        "limit_count": "Result Limit",
    }

    active_filters = {
        key: value
        for key, value in params.items()
        if value not in (None, "", False)
    }

    logger.info("=" * 60)
    logger.info("New search submitted")
    logger.info("-" * 60)

    if not active_filters:
        logger.info("No filters selected.")
    else:
        for key, value in active_filters.items():
            label = friendly_labels.get(key, key.replace("_", " ").title())
            logger.info("%-22s: %s", label, value)

    logger.info("=" * 60)


def log_event(message: str, level: str = "info") -> None:
    """
    Convenience helper for logging a one-off event (e.g. scraper
    started, scraper finished, error occurred) at a given level:
    'debug', 'info', 'warning', 'error', or 'critical'.
    """
    logger = get_logger()
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message)


if __name__ == "__main__":
    # Quick manual test
    demo_logger = get_logger()
    demo_logger.info("Logger initialized (%s)", datetime.now().isoformat())
    log_search_filters(
        {
            "estate_number": "",
            "county": "",
            "estate_status": "",
            "estate_type": "",
            "party_type": "",
            "last_name": "",
            "first_name": "",
            "filing_date_type": "",
            "filing_date_from": "",
            "filing_date_to": "",
            "filing_date_exact": "",
            "headless": True,
            "debug": False,
            "limit_results": True,
            "limit_count": "100",
        }
    )