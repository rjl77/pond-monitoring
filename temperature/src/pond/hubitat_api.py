import urllib.parse

import requests

from pond.config import require


def _base_url():
    host = require("HUBITAT_HOST")
    app_id = require("HUBITAT_APP_ID")
    return f"http://{host}/apps/api/{app_id}"


def _token():
    return require("HUBITAT_TOKEN")


def get_device_attribute(device_id, attribute):
    """Return an attribute value from a Hubitat Maker API device."""

    url = (
        f"{_base_url()}/devices/{device_id}/attribute/"
        f"{urllib.parse.quote(attribute, safe='')}"
    )

    response = requests.get(
        url,
        params={"access_token": _token()},
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict) and "value" in data:
        return data["value"]

    raise RuntimeError(
        f"Unexpected Hubitat response for device {device_id} attribute {attribute}"
    )


def send_device_command(device_id, command, argument=None):
    """Send a Maker API command to a Hubitat device."""

    command = urllib.parse.quote(str(command), safe="")

    url = f"{_base_url()}/devices/{device_id}/{command}"

    if argument is not None:
        argument = urllib.parse.quote(str(argument), safe="")
        url += f"/{argument}"

    response = requests.get(
        url,
        params={"access_token": _token()},
        timeout=10,
    )
    response.raise_for_status()

    return response
