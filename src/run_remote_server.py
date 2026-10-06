"""Run on all interfaces while displaying usable IPv4 URLs in the startup log."""
import copy
import ipaddress
import logging
import socket

import uvicorn


def remote_urls(port=8000):
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM
        )}
    except OSError:
        addresses = set()
    usable = sorted(address for address in addresses if not (
        ipaddress.ip_address(address).is_loopback
        or ipaddress.ip_address(address).is_link_local
        or ipaddress.ip_address(address).is_unspecified
        or ipaddress.ip_address(address).is_multicast
    ))
    return [f"http://{address}:{port}" for address in usable]


class RemoteAddressFilter(logging.Filter):
    def __init__(self, urls):
        super().__init__()
        self.urls = urls

    def filter(self, record):
        if str(record.msg).startswith("Uvicorn running on ") and self.urls:
            record.msg = "Uvicorn running on %s (Press CTRL+C to quit)"
            record.args = (", ".join(self.urls),)
            record.color_message = record.msg
        return True


def main():
    urls = remote_urls()
    if not urls:
        print("LAN IP could not be detected. Run ipconfig to find this computer's IPv4 address.", flush=True)
    config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    config.setdefault("filters", {})["remote_address"] = {
        "()": RemoteAddressFilter, "urls": urls,
    }
    config["handlers"]["default"].setdefault("filters", []).append("remote_address")
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, log_config=config)


if __name__ == "__main__":
    main()
