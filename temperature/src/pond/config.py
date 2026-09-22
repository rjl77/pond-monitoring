import os
from pathlib import Path


DEFAULT_CONFIG_FILE = Path("/opt/pond-collector/config/pond.env")


def load_env(path=DEFAULT_CONFIG_FILE):
    """Load KEY=VALUE settings without overwriting existing environment variables."""

    path = Path(path)

    if not path.is_file():
        raise RuntimeError(f"Configuration file not found: {path}")

    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise RuntimeError(
                f"Invalid configuration line {line_number}: expected KEY=VALUE"
            )

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise RuntimeError(
                f"Invalid configuration line {line_number}: empty key"
            )

        os.environ.setdefault(key, value)


def require(name):
    """Return a required configuration value."""

    value = os.environ.get(name)

    if value is None or value == "":
        raise RuntimeError(f"Required configuration value is missing: {name}")

    return value


def get(name, default=None):
    return os.environ.get(name, default)


def get_int(name, default=None):
    value = os.environ.get(name)

    if value is None:
        if default is None:
            raise RuntimeError(f"Required configuration value is missing: {name}")
        return default

    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Configuration value {name} must be an integer")


def get_bool(name, default=False):
    value = os.environ.get(name)

    if value is None:
        return default

    value = value.strip().lower()

    if value in ("1", "true", "yes", "on"):
        return True

    if value in ("0", "false", "no", "off"):
        return False

    raise RuntimeError(
        f"Configuration value {name} must be true/false"
    )
