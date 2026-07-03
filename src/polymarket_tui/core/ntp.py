"""Minimal SNTP client (stdlib only) to measure local clock offset.

The offset is applied to the displayed clock so the UI shows network-true time
even if the system clock drifts. One UDP round trip; failures return None.
"""

from __future__ import annotations

import socket
import struct
import time

NTP_SERVERS = ["time.cloudflare.com", "time.apple.com", "pool.ntp.org"]
NTP_PORT = 123
# Seconds between the NTP epoch (1900) and the Unix epoch (1970).
NTP_DELTA = 2_208_988_800


def sntp_offset(timeout: float = 2.0) -> float | None:
    """Clock offset in seconds (positive = system clock is behind true time).

    Standard SNTP: offset = ((t1 - t0) + (t2 - t3)) / 2 where t0/t3 are local
    send/receive times and t1/t2 are server receive/transmit times.
    """
    packet = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3 (client)
    for server in NTP_SERVERS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                t0 = time.time()
                sock.sendto(packet, (server, NTP_PORT))
                data, _ = sock.recvfrom(48)
                t3 = time.time()
            if len(data) < 48:
                continue
            unpacked = struct.unpack("!12I", data)
            t1 = unpacked[8] + unpacked[9] / 2**32 - NTP_DELTA  # receive ts
            t2 = unpacked[10] + unpacked[11] / 2**32 - NTP_DELTA  # transmit ts
            if t1 <= 0 or t2 <= 0:
                continue
            return ((t1 - t0) + (t2 - t3)) / 2
        except OSError:
            continue
    return None
