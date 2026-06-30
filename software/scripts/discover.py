#!/usr/bin/env python3
"""Discover LCD devices on the LAN. Cache check → parallel mDNS + UDP sweep."""

import json
import os
import re
import socket
import subprocess
import sys
import time
import concurrent.futures
import urllib.request
import threading

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
LCD_PORT = 3000

# Re-discovery throttle: when a hook can't reach the cached IP it asks us to
# rescan, but a device that's simply offline shouldn't trigger a full LAN sweep
# on every single event.
SCAN_THROTTLE_PATH = os.path.expanduser("~/.config/autonomous-lcd-scan.last")
SCAN_THROTTLE_SECONDS = 60
# Warning rate-limit: don't nag the user on every event while the device is down.
WARN_PATH = os.path.expanduser("~/.config/autonomous-lcd-warn.last")
WARN_SECONDS = 600


def cache_check():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        return []

    found = []
    for dev in cfg.get("devices", []):
        ip = dev.get("last_known_ip")
        if not ip:
            continue
        try:
            req = urllib.request.Request(f"http://{ip}:{LCD_PORT}/status")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                info = json.loads(resp.read())
                if info.get("device_id"):
                    found.append({"device_id": info["device_id"], "ip": ip})
        except Exception:
            pass
    return found


def _run_dns_sd(args, timeout=2):
    try:
        proc = subprocess.Popen(
            ["dns-sd"] + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            stdout, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
        return stdout
    except FileNotFoundError:
        return ""


def mdns_discover():
    stdout = _run_dns_sd(["-B", "_autonomous-lcd._tcp"], timeout=2)

    services = []
    for line in stdout.splitlines():
        if "Add" in line and "_autonomous-lcd._tcp" in line:
            parts = line.split()
            if len(parts) >= 7:
                services.append(parts[6])

    if not services:
        return []

    found = []
    for svc in services:
        out = _run_dns_sd(["-L", svc, "_autonomous-lcd._tcp"], timeout=2)
        hostname = None
        for line in out.splitlines():
            if "can be reached at" in line:
                m = re.search(r"can be reached at\s+(\S+)", line)
                if m:
                    hostname = m.group(1)
                    break
        if not hostname:
            continue

        out = _run_dns_sd(["-G", "v4", hostname], timeout=2)
        for line in out.splitlines():
            if "Add" in line:
                m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    ip = m.group(1)
                    try:
                        req = urllib.request.Request(f"http://{ip}:{LCD_PORT}/status")
                        with urllib.request.urlopen(req, timeout=1) as resp:
                            info = json.loads(resp.read())
                            if info.get("device_id"):
                                found.append({"device_id": info["device_id"], "ip": ip})
                    except Exception:
                        pass
                    break
    return found


def get_subnets():
    try:
        out = subprocess.check_output(["ifconfig"], text=True)
    except Exception:
        return []
    subnets = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet ") and "127.0.0.1" not in line:
            m = re.search(r"inet\s+(\d+\.\d+\.\d+)\.\d+", line)
            if m:
                subnets.append(m.group(1))
    return subnets


def udp_sweep(subnets):
    def probe(ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.sendto(b"AUTONOMOUS_LCD_PROBE?", (ip, 49152))
            data, _ = s.recvfrom(1024)
            return json.loads(data), ip
        except Exception:
            return None, None
        finally:
            s.close()

    candidates = []
    for subnet in subnets:
        candidates.extend(f"{subnet}.{i}" for i in range(1, 255))

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(probe, ip) for ip in candidates]
        for f in concurrent.futures.as_completed(futures):
            info, ip = f.result()
            if info and info.get("device_id"):
                found.append({"device_id": info["device_id"], "ip": ip})
    return found


def parallel_scan():
    results = {"mdns": [], "udp": []}
    subnets = get_subnets()

    def run_mdns():
        results["mdns"] = mdns_discover()

    def run_udp():
        if subnets:
            results["udp"] = udp_sweep(subnets)

    t1 = threading.Thread(target=run_mdns)
    t2 = threading.Thread(target=run_udp)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    seen = set()
    merged = []
    for dev in results["mdns"] + results["udp"]:
        did = dev["device_id"]
        if did not in seen:
            seen.add(did)
            merged.append(dev)
    return merged


def _update_cached_ip(device_id, ip):
    """Persist a freshly-discovered IP back into the config cache."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        return
    changed = False
    for dev in cfg.get("devices", []):
        if dev.get("device_id") == device_id and dev.get("last_known_ip") != ip:
            dev["last_known_ip"] = ip
            changed = True
    if changed:
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass


def _throttled(path, window):
    try:
        last = float(open(path).read().strip())
        return (time.time() - last) < window
    except Exception:
        return False


def _stamp(path):
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def reconnect(device_id):
    """Locate a device's current IP via a LAN scan and refresh the cached IP.

    Throttled (SCAN_THROTTLE_SECONDS) so back-to-back hook failures from an
    offline device don't each trigger a full sweep. Returns the IP on success,
    else None. Used by the hooks to recover when DHCP hands the device a new IP.
    """
    if _throttled(SCAN_THROTTLE_PATH, SCAN_THROTTLE_SECONDS):
        return None
    _stamp(SCAN_THROTTLE_PATH)
    match = None
    for d in parallel_scan():
        _update_cached_ip(d["device_id"], d["ip"])
        if d["device_id"] == device_id:
            match = d["ip"]
    return match


def warn_user(message):
    """Surface a non-blocking warning to the Claude Code user via systemMessage.

    Rate-limited (WARN_SECONDS) so an offline display doesn't warn on every
    event. Safe on both Stop and Notification hooks (printed to stdout, exit 0).
    """
    if _throttled(WARN_PATH, WARN_SECONDS):
        return
    _stamp(WARN_PATH)
    try:
        print(json.dumps({"systemMessage": message}))
    except Exception:
        pass


def main():
    found = cache_check()
    if found:
        print(json.dumps(found))
        return

    found = parallel_scan()
    if found:
        print(json.dumps(found))
    else:
        print(json.dumps({"error": "not_found"}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
