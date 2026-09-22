import json
import logging
from pathlib import Path


log = logging.getLogger("pond_collector")

DEFAULT_JOURNAL_FILE = Path(
    "/opt/pond-collector/runtime/sensor_journal.log"
)


def append(points, path=DEFAULT_JOURNAL_FILE):
    """
    Append InfluxDB points to the offline journal.

    Accepts either one point dict or a list of point dicts.
    Stores one JSON object per line.
    """

    if points is None:
        return

    if isinstance(points, dict):
        points = [points]

    if not isinstance(points, list):
        raise TypeError(
            f"Journal points must be dict or list[dict], got {type(points)}"
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a") as file:
        for point in points:
            if isinstance(point, dict):
                file.write(json.dumps(point) + "\n")
            else:
                log.warning(
                    "Skipping non-dict journal entry: %s",
                    type(point),
                )

    log.info("Appended data to offline journal.")


def flush(client, path=DEFAULT_JOURNAL_FILE):
    """
    Write pending journal entries to InfluxDB.

    Also accepts the historical format where a JSON list of
    points was stored on one line.

    Returns the number of points successfully flushed.
    """

    path = Path(path)

    if not path.exists():
        return 0

    points = []

    with path.open("r") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid journal JSON at line {line_number}: {exc}"
                ) from exc

            if isinstance(item, dict):
                points.append(item)

            elif isinstance(item, list):
                points.extend(
                    entry for entry in item
                    if isinstance(entry, dict)
                )

            else:
                log.warning(
                    "Skipping unknown journal item type at line %d: %s",
                    line_number,
                    type(item),
                )

    if not points:
        return 0

    result = client.write_points(points)

    if not result:
        raise RuntimeError(
            "InfluxDB did not confirm journal write"
        )

    # Only clear the journal after Influx has confirmed the write.
    path.write_text("")

    log.info(
        "Flushed %d points from offline journal.",
        len(points),
    )

    return len(points)
