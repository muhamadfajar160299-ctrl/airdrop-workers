#!/usr/bin/env python3
"""Free-mint radar screening (GitHub Actions / Plan B).

No secrets: only public sources + public BSC RPC.
- MintRadar index + per-contract label files (datt.my)
- Boltbook Alphapedia (en/zh) + Alpha Board
- AgenticMint open collections
- H-eartbreaker Gist feed

Green label ("hijau") + contract bytecode on-chain -> candidate.
Yellow/red -> recorded as seen-skipped. No label (404) -> unverified, recorded.
State: state/seen.json {addresses[], watermark}. Findings: findings/latest.json.

Fetching uses curl (preinstalled on ubuntu-latest runners): Boltbook pages
break Python urllib with IncompleteRead, curl handles them fine.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "state", "seen.json")
FINDINGS_PATH = os.path.join(ROOT, "findings", "latest.json")
ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")
RPC_URL = "https://bsc-dataseed.bnbchain.org"
TIMEOUT = 25
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

SOURCES = {
    "mintradar_index": "https://datt.my/data/kontrak/index.json",
    "alphapedia_en": "https://boltbook.fun/alphapedia?lang=en",
    "alphapedia_zh": "https://boltbook.fun/alphapedia?lang=zh",
    "alpha_board": "https://boltbook.fun/b/alpha?topic=airdrop&lang=en",
    "agenticmint": "https://agenticmint.ai/api/collections",
    "gist": "https://gist.githubusercontent.com/H-eartbreaker/30125fbc8f78a4c8a71fcaa3e6d14bdb/raw/nft-feed.json",
}


def curl(url, data=None):
    """Returns (body_bytes, http_status). Raises on curl failure."""
    cmd = ["curl", "-sS", "-L", "--max-time", str(TIMEOUT), "-A", UA,
           "-w", "\n%{http_code}"]
    if data is not None:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json",
                "--data", data]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT + 10)
    if r.returncode != 0:
        raise RuntimeError(f"curl exit {r.returncode}: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    out = r.stdout
    try:
        body, status = out.rsplit(b"\n", 1)
        return body, int(status.decode().strip())
    except (ValueError, IndexError):
        raise RuntimeError("could not parse curl http status")


def fetch_json(url):
    body, status = curl(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    return json.loads(body.decode("utf-8", "replace"))


def fetch_text(url):
    body, status = curl(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    return body.decode("utf-8", "replace")


def get_label(addr):
    """MintRadar label for an address: (label, name); label None on 404."""
    body, status = curl(f"https://datt.my/data/kontrak/{addr.lower()}.json")
    if status == 404:
        return None, ""
    if status != 200:
        raise RuntimeError(f"HTTP {status} for label {addr}")
    data = json.loads(body.decode("utf-8", "replace"))
    return (data.get("label") or "").strip().lower(), data.get("name") or ""


def has_code(addr):
    """True if the address hosts contract bytecode (eth_getCode)."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "eth_getCode",
        "params": [addr, "latest"],
    })
    body, status = curl(RPC_URL, data=payload)
    if status != 200:
        raise RuntimeError(f"RPC HTTP {status}")
    res = json.loads(body.decode())
    code = res.get("result") or "0x"
    return code not in ("0x", "0X", "")


def main():
    with open(STATE_PATH) as f:
        state = json.load(f)
    seen = set(a.lower() for a in state.get("addresses", []))
    watermark = int(state.get("watermark", 0))
    errors = []
    new_green, new_unverified, skipped = [], [], []
    processed = set()

    def classify(addr, name, source):
        addr = addr.lower()
        if not addr or addr in seen or addr in processed:
            return
        processed.add(addr)
        try:
            label, label_name = get_label(addr)
        except Exception as e:
            errors.append(f"label {addr} ({source}): {e}")
            return
        name = name or label_name or addr
        if label is None:
            new_unverified.append({"address": addr, "name": name, "source": source, "label": "unverified"})
            return
        if label == "hijau":
            try:
                live = has_code(addr)
            except Exception as e:
                errors.append(f"eth_getCode {addr}: {e}")
                live = False
            if live:
                new_green.append({"address": addr, "name": name, "source": source, "label": "hijau"})
            else:
                skipped.append({"address": addr, "name": name, "source": source, "reason": "no contract code on-chain"})
        else:
            skipped.append({"address": addr, "name": name, "source": source, "reason": f"label {label}"})

    # 1. MintRadar index: entries newer than watermark
    try:
        index = fetch_json(SOURCES["mintradar_index"])
        contracts = index.get("contracts", [])
        new_wm = watermark
        for c in contracts:
            try:
                new_wm = max(new_wm, int(c.get("checked_at", 0)))
            except (TypeError, ValueError):
                pass
        for c in contracts:
            try:
                if int(c.get("checked_at", 0)) > watermark:
                    classify(c.get("address", ""), c.get("name", ""), "mintradar")
            except (TypeError, ValueError):
                continue
        watermark = new_wm
    except Exception as e:
        errors.append(f"mintradar index: {e}")

    # 2-5. Address-rotating sources: collect unseen addresses, classify each
    for key in ("alphapedia_en", "alphapedia_zh", "alpha_board", "agenticmint", "gist"):
        try:
            text = fetch_text(SOURCES[key])
        except Exception as e:
            errors.append(f"{key}: {e}")
            continue
        for addr in sorted(set(ADDR_RE.findall(text))):
            classify(addr, "", key)

    seen |= processed
    state["addresses"] = sorted(seen)
    state["watermark"] = watermark
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)

    findings = {"new_green": new_green, "new_unverified": new_unverified,
                "skipped": skipped, "errors": errors}
    os.makedirs(os.path.dirname(FINDINGS_PATH), exist_ok=True)
    with open(FINDINGS_PATH, "w") as f:
        json.dump(findings, f, indent=1, sort_keys=True)

    print(f"green={len(new_green)} unverified={len(new_unverified)} "
          f"skipped={len(skipped)} errors={len(errors)} seen={len(seen)}")
    for g in new_green:
        print("GREEN:", g["name"], g["address"], f"({g['source']})")
    for e in errors:
        print("ERROR:", e, file=sys.stderr)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"new_green_count={len(new_green)}\n")


if __name__ == "__main__":
    main()
