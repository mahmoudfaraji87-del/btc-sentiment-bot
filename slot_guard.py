"""
Slot guard
----------
Prints "run" or "skip" so the GitHub workflow can decide whether to scrape.

Logic:
  The day is divided into 6-hour slots (00:00, 06:00, 12:00, 18:00 UTC).
  If the log file already contains a row for the CURRENT slot that has real
  data in it (not an all-empty row from a failed attempt), we print "skip"
  and the workflow stops before spending any ScraperAPI credits.
  Otherwise we print "run" and the scraper goes ahead.

This means: retry until we get the data, then stop for the rest of the slot.

Usage:
  python3 slot_guard.py <csv_path> <first_data_col> <last_data_col>
Example:
  python3 slot_guard.py data/sentiment_log.csv 1 5

Uses only the Python standard library so it can run before pip install.
"""

import sys
import os
import csv
from datetime import datetime, timezone

SLOT_HOURS = 6


def main():
    if len(sys.argv) < 4:
        print("run")  # fail open: if the guard is misconfigured, still collect data
        return

    log_file = sys.argv[1]
    first_col = int(sys.argv[2])
    last_col = int(sys.argv[3])

    now = datetime.now(timezone.utc)
    slot_start = now.replace(
        hour=(now.hour // SLOT_HOURS) * SLOT_HOURS,
        minute=0, second=0, microsecond=0,
    )

    if not os.path.isfile(log_file):
        print("run")
        return

    try:
        with open(log_file, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
    except Exception:
        print("run")
        return

    # Walk backwards from the newest row until we fall out of the current slot.
    for row in reversed(rows[1:]):
        if not row:
            continue
        raw_ts = row[0].replace(" UTC", "").strip()
        try:
            ts = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if ts < slot_start:
            break  # older than this slot; nothing useful left to find

        has_data = any(
            i < len(row) and row[i].strip() != ""
            for i in range(first_col, last_col + 1)
        )
        if has_data:
            print("skip")
            return

    print("run")


if __name__ == "__main__":
    main()
