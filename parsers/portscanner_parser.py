
from concurrent.futures import ThreadPoolExecutor, as_completed
import socket
from typing import List, Dict, Any

from core import config, utils


# Default common ports to check. Keep this short to be fast by default.
DEFAULT_PORTS = [
    20,21,22,23,25,49,53,67,68,69,80,110,111,119,123,135,
    137,138,139,143,161,162,179,389,427,443,445,465,500,
    512,513,514,515,520,587,593,623,636,989,990,993,995,
    1025,1080,1194,1433,1434,1521,1701,1723,1812,1813,
    1900,2049,2082,2083,2086,2087,2095,2096,2181,2375,
    2376,2483,2484,3000,3001,3128,3268,3269,3306,3389,
    3690,4444,4567,5000,5060,5061,5432,5601,5672,5683,
    5900,5938,5984,6000,6379,6443,6667,7001,7002,7070,
    7443,7777,8000,8008,8009,8080,8081,8443,8888,9000,
    9042,9090,9092,9200,9418,9443,9999,10000,11211,
    27017,27018,27019]


def _check_port(ip: str, port: int, timeout: float = 1.0) -> Dict[str, Any]:
    """Attempt a TCP connect to (ip, port). Return info dict on success or
    {'port': port, 'open': False} on failure.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(0.5)
            banner = ""
            try:
                banner = s.recv(1024).decode(errors="ignore").strip()
            except Exception:
                pass

            service = None
            try:
                service = socket.getservbyport(port, "tcp")
            except Exception:
                service = None

            return {"port": port, "open": True, "service": service, "banner": banner}
    except Exception:
        return {"port": port, "open": False}


def run(domain: str) -> Dict[str, Any]:
    """Entry point called by the parsers manager. Returns a dict describing
    the scan results and the saved output path.

    Output keys:
      - ip: resolved IP or error
      - open_ports: list of open port numbers
      - details: list of strings with per-port details
      - file: saved results path (if saved)
    """
    try:
        ip = socket.gethostbyname(domain)
    except Exception as e:
        utils.log(f"[PORTSCAN] Could not resolve {domain}: {e}", "warn")
        return {"ip": None, "error": "unresolvable"}

    ports = DEFAULT_PORTS
    timeout = 1.0

    utils.log(f"[PORTSCAN] Scanning {ip} ({domain}) on {len(ports)} ports ...")

    results = []
    open_ports: List[int] = []

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
        futures = {ex.submit(_check_port, ip, p, timeout): p for p in ports}
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception:
                continue
            results.append(r)
            if r.get("open"):
                open_ports.append(r["port"])

    # prepare human readable lines and save them
    lines = []
    for r in sorted(results, key=lambda x: x.get("port", 0)):
        if r.get("open"):
            svc = r.get("service") or "unknown"
            banner_lines = (r.get("banner") or "").splitlines()
            banner = banner_lines[0][:200] if banner_lines else ""
            lines.append(f"{ip}:{r['port']} - {svc} - {banner}")
        else:
            lines.append(f"{ip}:{r['port']} - closed")

    filename = f"ports_{domain.replace('/', '_')}_{utils.timestamp()}.txt"
    saved = utils.save_list(filename, lines)

    summary = {
        "ip": ip,
        "open_ports": sorted(open_ports),
        "details": lines,
        "file": saved,
    }
    utils.log(f"[PORTSCAN] Completed scan for {domain}: {len(open_ports)} open ports.", "good")
    return summary
import nmap

def scan_ports(target):
    nm = nmap.PortScanner()
    nm.scan(target, arguments='-sS -Pn')
    return nm.all_hosts()
