import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import random
import re
import sys
import threading
import time
from urllib.parse import quote, unquote, urljoin, urlparse, parse_qs

from curl_cffi import requests as cr
from curl_cffi.requests import AsyncSession
import telebot
from telebot import types

# Ensure UTF-8 output encoding across Windows / Linux consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# CONFIGURATION
# ============================================================

DEVELOPER = "@xoxhunterxd"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

BLOG = "https://blog.gangstarnewyorkapk.com/"
ADCADG = "insurance,online_colleges,study_abroad,finance,loan"
SKIP_PATHS = ("about-us", "contact-us", "dmca", "privacy-policy",
              "category", "author", "feed", "wp-")

PROFILES = [
    dict(t="chrome142", ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
         brands='"Chromium";v="142", "Google Chrome";v="142", "Not-A.Brand";v="99"', plat="Windows"),
    dict(t="chrome136", ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
         brands='"Chromium";v="136", "Google Chrome";v="136", "Not-A.Brand";v="99"', plat="Windows"),
    dict(t="chrome133a", ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
         brands='"Chromium";v="133", "Google Chrome";v="133", "Not-A.Brand";v="99"', plat="macOS"),
    dict(t="chrome131", ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
         brands='"Chromium";v="131", "Google Chrome";v="131", "Not-A.Brand";v="99"', plat="Linux"),
    dict(t="chrome124", ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
         brands='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"', plat="Windows"),
    dict(t="safari184", ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
         brands=None, plat="macOS"),
    dict(t="firefox144", ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
         brands=None, plat="Windows"),
    dict(t="firefox135", ua="Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
         brands=None, plat="Linux"),
    dict(t="chrome131_android", ua="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
         brands='"Chromium";v="131", "Google Chrome";v="131", "Not-A.Brand";v="99"', plat="Android", mobile="?1"),
]

LANGS = [
    "en-US,en;q=0.9", "en-GB,en;q=0.8,en-US;q=0.7",
    "en-US,en;q=0.9,hi;q=0.8", "en;q=0.9", "en-CA,en;q=0.8,fr-CA;q=0.6"
]

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def rum_beacon(s, host, referer):
    payload = json.dumps({
        "resources": [], "referrer": referer, "eventType": 3,
        "versions": {"js": "2026.6.0", "fl": "2024.11.0"},
        "pageloadId": f"{random.randint(10**10, 10**11):x}-{random.randint(10**10, 10**11):x}-"
                      f"{random.randint(10**10, 10**11):x}-{random.randint(10**10, 10**11):x}",
        "sessionKey": f"{random.randint(10**10, 10**11):x}",
        "swift": False, "noscript": False, "performance": {},
    })
    try:
        s.post(f"https://{host}/cdn-cgi/rum?of_c=0&v=2026.6.0", data=payload,
               headers={"Content-Type": "text/plain;charset=UTF-8",
                        "Origin": f"https://{host}", "Referer": referer},
               timeout=15)
    except Exception:
        pass


def build_session():
    p = random.choice(PROFILES)
    s = cr.Session(impersonate=p["t"])
    h = {"User-Agent": p["ua"], "Accept-Language": random.choice(LANGS)}
    if p["brands"]:
        h["sec-ch-ua"] = p["brands"]
        h["sec-ch-ua-platform"] = f'"{p["plat"]}"'
        if "mobile" in p:
            h["sec-ch-ua-mobile"] = p["mobile"]
    s.headers.update(h)
    s.verify = False
    return s, p["t"]


def parse_proxy_any(spec):
    spec = (spec or "").strip()
    if not spec:
        return None
    m = re.match(r"^(https?|socks[45]h?)://(.+)$", spec, re.I)
    scheme, rest = (m.group(1).lower(), m.group(2)) if m else ("http", spec)

    def safe_auth(user, passwd):
        u = quote(unquote(user), safe="")
        p = quote(unquote(passwd), safe="") if passwd else ""
        return f"{u}:{p}" if p else u

    if "@" in rest:
        userinfo, hostpart = rest.rsplit("@", 1)
        user, _, passwd = userinfo.partition(":")
        return f"{scheme}://{safe_auth(user, passwd)}@{hostpart}"
    parts = rest.split(":")
    if len(parts) == 4 and parts[0]:
        return f"{scheme}://{safe_auth(parts[2], parts[3])}@{parts[0]}:{parts[1]}"
    if len(parts) == 2 and parts[0]:
        return f"{scheme}://{parts[0]}:{parts[1]}"
    if len(parts) == 1 and parts[0]:
        return f"{scheme}://{parts[0]}:8080"
    return None


def mask_proxy(p: str) -> str:
    if not p:
        return "None"
    m = re.match(r"^(https?|socks[45]h?)://([^:]+):([^@]+)@(.+)$", p)
    if m:
        return f"{m.group(1)}://{m.group(2)}:***@{m.group(4)}"
    return p


def make_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "[░░░░░░░░░░]"
    filled = max(0, min(length, int(length * (current / total))))
    return f"[{'█' * filled}{'░' * (length - filled)}]"


async def async_check_proxy(proxy_url: str, timeout: int = 5) -> dict:
    """
    Asynchronously probes proxy connectivity, latency, protocol, and detects
    whether the exit IP is Rotating or Static.
    """
    parsed = parse_proxy_any(proxy_url)
    if not parsed:
        return {"live": False, "reason": "Invalid format", "proxy": proxy_url}

    protocol = "SOCKS5" if "socks5" in parsed.lower() else "HTTP"
    t0 = time.perf_counter()
    try:
        async with AsyncSession(
            impersonate="chrome131",
            proxies={"http": parsed, "https": parsed},
            verify=False
        ) as s:
            r1 = await s.get("https://api.ipify.org?format=json", timeout=timeout)
            latency = time.perf_counter() - t0
            if r1.status_code != 200:
                return {"live": False, "reason": f"HTTP {r1.status_code}", "proxy": parsed, "latency": latency}

            ip1 = r1.json().get("ip", "") if "{" in r1.text else r1.text.strip()

            # Second probe to test if IP rotates
            proxy_type = "Static"
            try:
                r2 = await s.get("https://api.ipify.org?format=json", timeout=timeout)
                ip2 = r2.json().get("ip", "") if "{" in r2.text else r2.text.strip()
                if ip1 and ip2 and ip1 != ip2:
                    proxy_type = "Rotating"
            except Exception:
                pass

            return {
                "live": True,
                "proxy": parsed,
                "type": proxy_type,
                "protocol": protocol,
                "ip": ip1,
                "latency": latency
            }
    except Exception as e:
        latency = time.perf_counter() - t0
        err = str(e)
        if "Failed to connect" in err or "Connection refused" in err:
            err = "Connection Refused / Offline"
        elif "timed out" in err or "Timeout" in err:
            err = "Connection Timed Out"
        elif "Proxy" in err:
            err = "Proxy Handshake Error"
        else:
            err = err[:35]
        return {"live": False, "reason": err, "proxy": parsed, "latency": latency}


def check_proxy_live(proxy_url: str, timeout: int = 5) -> dict:
    """Sync wrapper for async_check_proxy."""
    try:
        return asyncio.run(async_check_proxy(proxy_url, timeout=timeout))
    except Exception as e:
        return {"live": False, "reason": str(e)[:35], "proxy": proxy_url, "latency": 0.0}


class ProxyManager:
    """Thread-safe proxy pool with persistence and Static/Rotating metadata."""
    def __init__(self, txt_path="proxies.txt", json_path="proxies.json"):
        self.txt_path = txt_path
        self.json_path = json_path
        self.proxies = []
        self.meta = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        with self.lock:
            self.proxies = []
            self.meta = {}
            if os.path.isfile(self.json_path):
                try:
                    with open(self.json_path, "r", encoding="utf-8") as f:
                        self.meta = json.load(f)
                except Exception:
                    self.meta = {}

            if os.path.isfile(self.txt_path):
                try:
                    with open(self.txt_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                parsed = parse_proxy_any(line)
                                if parsed and parsed not in self.proxies:
                                    self.proxies.append(parsed)
                                    if parsed not in self.meta:
                                        self.meta[parsed] = {"type": "Static", "latency": 0.0, "ip": ""}
                    print(f"[*] Loaded {len(self.proxies)} proxies ({self.get_stats_unlocked()})", flush=True)
                except Exception as e:
                    print(f"[!] Could not load {self.txt_path}: {e}", flush=True)

    def save(self):
        try:
            with open(self.txt_path, "w", encoding="utf-8") as f:
                for p in self.proxies:
                    f.write(f"{p}\n")
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.meta, f, indent=2)
        except Exception as e:
            print(f"[!] Warning saving proxy storage: {e}", flush=True)

    def add(self, proxy_str: str, p_type: str = "Static", latency: float = 0.0, ip: str = "", protocol: str = "HTTP") -> bool:
        parsed = parse_proxy_any(proxy_str)
        if not parsed:
            return False
        with self.lock:
            if parsed not in self.proxies:
                self.proxies.append(parsed)
            self.meta[parsed] = {
                "type": p_type,
                "latency": latency,
                "ip": ip,
                "protocol": protocol,
                "updated_at": time.time()
            }
            self.save()
            return True

    def remove(self, proxy_str: str) -> bool:
        parsed = parse_proxy_any(proxy_str) or proxy_str
        with self.lock:
            changed = False
            if parsed in self.proxies:
                self.proxies.remove(parsed)
                changed = True
            if parsed in self.meta:
                del self.meta[parsed]
                changed = True
            if changed:
                self.save()
                return True
        return False

    def has(self, proxy_str: str) -> bool:
        parsed = parse_proxy_any(proxy_str) or proxy_str
        with self.lock:
            return parsed in self.proxies

    def get_random(self):
        with self.lock:
            if not self.proxies:
                return None
            # Prioritize rotating proxies if available
            rotating = [p for p in self.proxies if self.meta.get(p, {}).get("type") == "Rotating"]
            if rotating:
                return random.choice(rotating)
            return random.choice(self.proxies)

    def count(self) -> int:
        with self.lock:
            return len(self.proxies)

    def get_stats_unlocked(self) -> str:
        total = len(self.proxies)
        rotating = sum(1 for p in self.proxies if self.meta.get(p, {}).get("type") == "Rotating")
        static = total - rotating
        return f"{static} Static, {rotating} Rotating"

    def get_stats(self) -> dict:
        with self.lock:
            total = len(self.proxies)
            rotating = sum(1 for p in self.proxies if self.meta.get(p, {}).get("type") == "Rotating")
            static = total - rotating
            return {"total": total, "static": static, "rotating": rotating}

    def get_all(self) -> list:
        with self.lock:
            return list(self.proxies)

    def clear(self):
        with self.lock:
            self.proxies = []
            self.meta = {}
            self.save()


proxy_manager = ProxyManager()


async def async_scan_proxies_pipeline(proxy_list: list, max_concurrency: int = 25, on_progress=None):
    """
    High-performance async proxy pipeline with live statistics & progress bar.
    """
    sem = asyncio.Semaphore(max_concurrency)
    total = len(proxy_list)
    tested_count = 0
    live_results = []
    dead_results = []
    lock = asyncio.Lock()
    last_ui_update = 0.0

    async def worker(p):
        nonlocal tested_count, last_ui_update
        async with sem:
            res = await async_check_proxy(p, timeout=5)
            async with lock:
                tested_count += 1
                if res.get("live"):
                    live_results.append(res)
                else:
                    dead_results.append(res)

                now = time.time()
                if on_progress and (now - last_ui_update >= 1.5 or tested_count == total):
                    last_ui_update = now
                    static_count = sum(1 for r in live_results if r.get("type") == "Static")
                    rotating_count = len(live_results) - static_count
                    avg_lat = (sum(r.get("latency", 0.0) for r in live_results) / len(live_results)) if live_results else 0.0
                    on_progress({
                        "tested": tested_count,
                        "total": total,
                        "static": static_count,
                        "rotating": rotating_count,
                        "live": len(live_results),
                        "dead": len(dead_results),
                        "avg_latency": avg_lat,
                    })

    tasks = [worker(p) for p in proxy_list]
    await asyncio.gather(*tasks)
    return live_results, dead_results


def normalize(link):
    u = (link or "").strip()
    if not u:
        return None, None
    m = re.match(r"(?:https?://)?(?:link\.|m\.)?vipshort\.in/(.+?)/?$", u, re.I)
    if m:
        return "vipshort", f"https://link.vipshort.in/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:www\.)?arolinks\.com/(.+?)/?$", u, re.I)
    if m:
        return "arolinks", f"https://arolinks.com/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:www\.)?vplinks?\.in/(.+?)/?$", u, re.I)
    if m:
        return "vplink", f"https://vplink.in/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:m\.|www\.)?easysky\.in/(.+?)/?$", u, re.I)
    if m:
        return "easysky", f"https://m.easysky.in/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:www\.)?monteolympus\.com/s/(.+?)/?$", u, re.I)
    if m:
        return "monteolympus", f"https://monteolympus.com/s/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:www\.)?(?:shrinkme\.(?:click|io|org|net|cc)|shrinke\.me)/(.+?)/?$", u, re.I)
    if m:
        return "shrinkme", f"https://shrinkme.click/{m.group(1)}"
    m = re.match(r"(?:https?://)?(?:www\.)?dupload\.(?:net|xyz)/(.+?)/?$", u, re.I)
    if m:
        return "dupload", f"https://dupload.net/{m.group(1)}"
    if "/" not in u and "." not in u:
        return "vipshort", f"https://link.vipshort.in/{u}"
    return None, u


# ============================================================
# BYPASS LOGIC WITH LIVE STATUS CALLBACKS
# ============================================================

def walk_vipshort(s, short_url, notify):
    r = s.get(short_url, timeout=25)
    notify(f"[vip] {r.status_code} -> {r.url[:70]}")
    if "myphp" not in r.url:
        raise RuntimeError("expected the blog myphp hop — funnel layout changed?")

    if not re.search(r"[?&]p=\d", r.url):
        notify("[vip] search-hop variant detected — swapping slug via ri.php")
        time.sleep(random.uniform(1.5, 3.0))
        s.get(BLOG, timeout=25, headers={"Referer": r.url})
        r2 = s.get("https://open2get.in/ri.php", timeout=25, headers={"Referer": BLOG})
        m = re.search(r'(?:window|document)\.location(?:\.href)?\s*=\s*[\'"]'
                      r'(https://blog\.gangstarnewyorkapk\.com/myphp\.php[^\'"]+)', r2.text)
        if not m:
            raise RuntimeError("ri.php didn't reveal the internal slug")
        notify(f"[vip] internal slug hop: {m.group(1)[:60]}...")
        time.sleep(random.uniform(1.0, 2.0))
        return walk_vipshort(s, m.group(1), notify)

    time.sleep(random.uniform(2.5, 5.0))
    r = s.get(BLOG, timeout=25, headers={"Referer": r.url})
    if "wpsafelink" not in r.text.lower():
        raise RuntimeError("wpsafelink widget not injected — IP flagged")
    rum_beacon(s, "blog.gangstarnewyorkapk.com", BLOG)
    posts = [u for u in re.findall(r'href="(' + re.escape(BLOG) + r'[a-z0-9-]+/)"', r.text)
             if not any(k in u for k in SKIP_PATHS)]
    if not posts:
        raise RuntimeError("no ladder post permalink on the blog homepage")
    notify(f"[vip] ladder post: {posts[0][:60]}...")

    for vip in ("4", "3", "2"):
        time.sleep(random.uniform(3.5, 6.0))
        data = {"vip1": vip} if vip != "2" else {"vip1": "2", "g-recaptcha-response": ""}
        r = s.post(posts[0], data=data,
                   headers={"Origin": BLOG.rstrip("/"), "Referer": BLOG}, timeout=25)
        m = re.search(r'https://m\.vipshort\.in/[^"\'<>\s]+', r.text)
        if m:
            notify(f"[vip] ladder paid at vip1={vip}")
            return m.group(0)
    raise RuntimeError("ladder walked clean — no go-page URL")


def js_hop(html):
    m = (re.search(r'(?:window|document)\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]', html)
         or re.search(r'<meta[^>]+http-equiv="refresh"[^>]+url=([^\'">]+)', html, re.I))
    if not m and "h1 style" in html and "Opening Link" in html:
        m = re.search(r'href="([^"]+)"', html)
    return m.group(1).strip() if m else None


def walk_arolinks(s, short_url, notify):
    url, referer = short_url, short_url
    articles = 0
    for step in range(40):
        r = s.get(url, timeout=25, headers={"Referer": referer})
        referer = url
        host = re.search(r"https?://([^/]+)", url).group(1)

        if "arolinks.com" in host:
            if "ad_form_data" in r.text and step > 0:
                notify(f"[aro] go form served after {articles} gateway articles (hop {step})")
                return url, r.text
            notify(f"[aro] {step}: arolinks bounce (lap not finished yet)")

        m = js_hop(r.text)
        if m:
            url = urljoin(url, m)
            time.sleep(random.uniform(0.9, 2.2))
            continue

        # If on arolinks.com and no js_hop found, do NOT hit /readmore/ on arolinks
        if "arolinks.com" in host:
            if r.status_code in (403, 503) or "just a moment" in r.text.lower() or "challenge" in r.text.lower():
                notify(f"[aro] ⚠️ Cloudflare Challenge on Cloud IP (HTTP {r.status_code})")
                raise RuntimeError("Cloudflare blocked datacenter IP. Send '<url> <proxy>' to use a custom proxy.")

            # Check for fallback click here anchor
            anchor_m = re.search(r'<a[^>]+href=[\'"](https?://[^\'"]+)[\'"][^>]*>\s*(?:click here|open link|continue)', r.text, re.I)
            if anchor_m and "arolinks.com" not in anchor_m.group(1):
                url = anchor_m.group(1).strip()
                time.sleep(random.uniform(0.9, 2.2))
                continue

            notify(f"[aro] ⚠️ arolinks returned no redirect (HTTP {r.status_code}).")
            raise RuntimeError("arolinks returned no redirect. The link may be dead or expired.")

        # Gateway article (hittracks, entiredust, etc.): forge cookie, hit /readmore/
        s.cookies.set("adcadg", ADCADG, domain=host)
        articles += 1
        notify(f"[aro] {step}: gateway article #{articles} on {host} -> /readmore/")
        url = f"https://{host}/readmore/"
        time.sleep(random.uniform(5.0, 6.5))
    raise RuntimeError("walk ran out of hops — IP throttled? try --proxy")


def bypass_dupload(s, page_url, notify):
    notify(f"[dupload] inspecting {page_url[:60]}...")
    r = s.get(page_url, timeout=25)
    m = re.search(r'<form id="down".*?</form>', r.text, re.S)
    if not m:
        raise RuntimeError("no download2 form — page layout changed or dead link")
    fields = dict(re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"', m.group(0)))
    if fields.get("op") != "download2":
        raise RuntimeError(f"unexpected form op: {fields.get('op')!r}")
    fields["referer"] = page_url
    notify("[dupload] respecting countdown timer (4s)...")
    time.sleep(random.uniform(4.0, 5.5))

    r2 = s.post(page_url, data=fields,
                headers={"Origin": "https://dupload.net", "Referer": page_url},
                timeout=25, allow_redirects=False)
    if r2.status_code in (301, 302, 303, 307, 308):
        return r2.headers.get("location", "").strip()
    mm = (re.search(r'href="(https?://[^"]*/files/[^"]+)"', r2.text)
          or re.search(r'(https?://fs\d*\.dupload\.xyz/[^"\'<>\s]+)', r2.text))
    if mm:
        return mm.group(1)
    raise RuntimeError(f"download2 said {r2.status_code}, no CDN link surfaced")


def kill(s, go_page, html, host, notify):
    inputs = {}
    for tag in re.finditer(r'<input[^>]+>', html):
        t = tag.group(0)
        n = re.search(r'name="([^"]+)"', t)
        v = re.search(r'value="([^"]*)"', t)
        if n:
            inputs[n.group(1)] = v.group(1) if v else ""
    if "ad_form_data" not in inputs:
        raise RuntimeError("go form missing ad_form_data — dead slug or new layout")

    s.cookies.set("ab", "2", domain=host)
    if inputs.get("_csrfToken"):
        s.cookies.set("csrfToken", inputs["_csrfToken"], domain=host)
    rum_beacon(s, host, go_page)
    notify(f"[{host[:3]}] waiting out countdown timer (6s)...")
    time.sleep(random.uniform(5.5, 7.5))

    payload = dict(inputs)
    payload["_method"] = "POST"
    r = s.post(f"https://{host}/links/go", data=payload,
               headers={"Origin": f"https://{host}",
                        "Referer": go_page,
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest"},
               timeout=25)
    j = r.json() if r.text.strip().startswith("{") else {}
    if j.get("status") != "success" or not j.get("url"):
        raise RuntimeError(f"server said: {r.text[:140]}")
    return j["url"]


def visit_final(s, url, host, notify):
    try:
        r = s.get(url, timeout=20, headers={"Referer": f"https://{host}/"})
        notify(f"[visit] final hop: {r.status_code} ({url[:60]})")
    except Exception as e:
        if "SSL" in str(e) or "certificate" in str(e):
            try:
                r = s.get(url, timeout=20, verify=False,
                          headers={"Referer": f"https://{host}/"})
                notify(f"[visit] final hop: {r.status_code} [cert unverified]")
                return
            except Exception:
                pass
        notify(f"[visit] final hop note: {str(e)[:60]}")


def extract_vplink_destination(html):
    # 1. Primary: vplink.in custom direct "gt-link" anchor
    m = re.search(r'<a[^>]+id=[\'"]gt-link[\'"][^>]*href=[\'"]([^\'"]+)[\'"]', html)
    if not m:
        m = re.search(r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*id=[\'"]gt-link[\'"]', html)
    if m and m.group(1).strip() and not m.group(1).startswith("javascript:"):
        return m.group(1).strip()

    # 2. Secondary: any anchor with "Get link" text and non-javascript href
    m = re.search(r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>\s*Get link\s*</a>', html, re.I)
    if m and m.group(1).strip() and not m.group(1).startswith("javascript:"):
        return m.group(1).strip()

    return None


def kill_vplink(s, go_page, html, notify):
    direct = extract_vplink_destination(html)
    if direct:
        notify(f"[vplink] direct destination found in page: {direct[:60]}...")
        return direct

    inputs = {}
    for tag in re.finditer(r'<input[^>]+>', html):
        t = tag.group(0)
        n = re.search(r'name="([^"]+)"', t)
        v = re.search(r'value="([^"]*)"', t)
        if n:
            inputs[n.group(1)] = v.group(1) if v else ""

    if "ad_form_data" not in inputs:
        raise RuntimeError("go form missing ad_form_data — page layout changed?")
    notify(f"[vplink] harvested go form ({len(inputs)} fields)")

    s.cookies.set("ab", "2", domain="vplink.in")
    if inputs.get("_csrfToken"):
        s.cookies.set("csrfToken", inputs["_csrfToken"], domain="vplink.in")

    notify("[vplink] waiting out 5s counter...")
    time.sleep(5.2)

    payload = dict(inputs)
    payload["_method"] = "POST"
    r = s.post("https://vplink.in/links/go", data=payload, headers={
        "Origin": "https://vplink.in",
        "Referer": go_page,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest"
    }, timeout=25)

    j = r.json() if r.text.strip().startswith("{") else {}
    if j.get("status") != "success" or not j.get("url"):
        raise RuntimeError(f"links/go failed: {r.text[:140]}")
    return j["url"]


def walk_vplink(s, short_url, notify):
    url = short_url
    referer = short_url
    articles = 0

    for step in range(35):
        m_host = re.search(r"https?://([^/]+)", url)
        host = m_host.group(1) if m_host else ""
        notify(f"[vplink] hop {step}: [{host}] {url[:65]}")

        r = s.get(url, timeout=25, headers={"Referer": referer})
        referer = r.url
        m_host = re.search(r"https?://([^/]+)", r.url)
        host = m_host.group(1) if m_host else host

        # Check if vplink served the go form or direct destination
        if "vplink.in" in host:
            if "ad_form_data" in r.text and step > 0:
                notify(f"[vplink] go form served on vplink.in at hop {step}")
                return r.url, r.text
            direct = extract_vplink_destination(r.text)
            if direct and step > 0:
                notify(f"[vplink] direct destination found at hop {step}")
                return r.url, r.text
            notify(f"[vplink] {step}: vplink bounce / initial")

        # Check for JS trampoline redirect
        m = js_hop(r.text)
        if m:
            target = urljoin(r.url, m)
            if target.rstrip('/') != r.url.rstrip('/'):
                notify(f"[vplink] js -> {target[:65]}")
                url = target
                time.sleep(random.uniform(1.2, 2.0))
                continue

        # Gateway article page
        articles += 1
        s.cookies.set("adcadg", ADCADG, domain=host)
        if "entiredust" in host:
            s.cookies.set("_uocat", "value", domain=host)

        # Look for learn_more link
        m_lm = re.search(r'href="([^"]*learn_more\.php[^"]*)"', r.text)
        if m_lm:
            learn_more_target = urljoin(r.url, m_lm.group(1))
        elif "entiredust" in host:
            learn_more_target = f"https://{host}/studyscholorhiipss/learn_more.php"
        else:
            learn_more_target = f"https://{host}/learn_more.php"

        notify(f"[vplink] article #{articles} on {host} -> wait 5.5s")
        time.sleep(5.5)
        url = learn_more_target

    raise RuntimeError("vplink walk exceeded max hops without finding go form or destination")


def bypass_easysky(s, short_url, notify):
    slug = short_url.rstrip("/").split("/")[-1]
    notify(f"[sky] target: {short_url} (slug: {slug})")

    # Step 1: Initial request to m.easysky.in
    r1 = s.get(short_url, allow_redirects=True, timeout=25)
    notify(f"[sky] step 1: {r1.status_code} -> {r1.url[:65]}")

    # Extract base64 target for step 2
    m1 = re.search(r'name="go"\s+value="([^"]+)"', r1.text)
    if m1:
        try:
            u1 = base64.b64decode(m1.group(1)).decode()
        except Exception:
            u1 = f"https://easy.inyourcities.in?adlinkfly=/{slug}"
    else:
        u1 = f"https://easy.inyourcities.in?adlinkfly=/{slug}"
    notify(f"[sky] step 1 next hop: {u1[:65]}")

    # Step 2: Request easy.inyourcities.in
    r2 = s.get(u1, allow_redirects=True, timeout=25)
    notify(f"[sky] step 2: {r2.status_code} -> {r2.url[:65]}")

    m2 = re.search(r'name="go"\s+value="([^"]+)"', r2.text)
    if m2:
        try:
            u2 = base64.b64decode(m2.group(1)).decode()
        except Exception:
            u2 = f"https://w.gameswow.info///{slug}"
    else:
        u2 = f"https://w.gameswow.info///{slug}"
    notify(f"[sky] step 2 adlinkfly target: {u2[:65]}")

    # Step 3: Forge safelink_redirect to land directly on adLinkFly go page with proper Referer
    payload = json.dumps({"second_safelink_url": "", "safelink": u2})
    b64_payload = base64.b64encode(payload.encode()).decode()
    redir_url = f"https://easy.inyourcities.in/?safelink_redirect={b64_payload}"

    r3 = s.get(redir_url, headers={"Referer": "https://easy.inyourcities.in/"}, allow_redirects=True, timeout=25)
    notify(f"[sky] reached go page: {r3.url[:65]}")

    if "ad_form_data" not in r3.text:
        raise RuntimeError("Failed to land on adLinkFly go page (ad_form_data missing)")

    # Step 4: Harvest form inputs
    inputs = {}
    for tag in re.finditer(r'<input[^>]+>', r3.text):
        t = tag.group(0)
        n = re.search(r'name="([^"]+)"', t)
        v = re.search(r'value="([^"]*)"', t)
        if n:
            inputs[n.group(1)] = v.group(1) if v else ""

    host = re.search(r"https?://([^/]+)", r3.url).group(1)
    s.cookies.set("ab", "2", domain=host)
    if inputs.get("_csrfToken"):
        s.cookies.set("csrfToken", inputs["_csrfToken"], domain=host)

    notify(f"[sky] waiting out countdown timer (5.2s) on {host}...")
    time.sleep(5.2)

    # Step 5: Kill shot POST /links/go
    p = dict(inputs)
    p["_method"] = "POST"
    r_post = s.post(f"https://{host}/links/go", data=p, headers={
        "Origin": f"https://{host}",
        "Referer": r3.url,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest"
    }, timeout=25)

    j = r_post.json() if r_post.text.strip().startswith("{") else {}
    if j.get("status") == "success" and j.get("url"):
        final_url = j["url"]
        notify(f"[sky] extracted final destination: {final_url[:65]}...")
        return final_url

    raise RuntimeError(f"Server rejected links/go: {r_post.text[:140]}")


def bypass_monteolympus(s, short_url, notify):
    url = short_url.strip()
    if not url.endswith("/"):
        url += "/"
    notify(f"[monte] connecting to {url}")
    resp = s.get(url, allow_redirects=False, timeout=15)
    target_loc = None
    if resp.status_code in (301, 302, 303, 307, 308):
        target_loc = resp.headers.get("location") or resp.headers.get("Location")
        notify(f"[monte] redirect hop 1: {target_loc[:70]}...")

    if target_loc and "token=" not in target_loc:
        resp2 = s.get(target_loc, allow_redirects=False, timeout=15)
        if resp2.status_code in (301, 302, 303, 307, 308):
            target_loc = resp2.headers.get("location") or resp2.headers.get("Location")
            notify(f"[monte] redirect hop 2: {target_loc[:70]}...")

    token_b64 = None
    if target_loc and "token=" in target_loc:
        parsed = urlparse(target_loc)
        qs = parse_qs(parsed.query)
        token_b64 = qs.get("token", [None])[0]

    if not token_b64:
        m = re.search(r'token=([a-zA-Z0-9_\-=]+)', resp.text)
        if m:
            token_b64 = m.group(1)

    if not token_b64:
        raise ValueError("Could not extract destination token from MonteOlympus server.")

    missing = len(token_b64) % 4
    if missing:
        token_b64 += "=" * (4 - missing)

    final_url = base64.b64decode(token_b64).decode("utf-8", errors="replace")
    notify(f"[monte] destination resolved: {final_url[:70]}...")
    return final_url


def bypass_shrinkme(s, short_url, notify):
    slug = short_url.rstrip("/").split("/")[-1]
    notify(f"[shrink] fetching gate for slug: {slug}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36",
        "Referer": "https://themezon.net/",
    }

    t0 = time.time()
    r = s.get(f"https://en.mrproblogger.com/{slug}", headers=headers, timeout=20)

    m_csrf = re.search(r'name="_csrfToken"[^>]*value="([^"]+)"', r.text)
    m_ad = re.search(r'name="ad_form_data"[^>]*value="([^"]+)"', r.text)
    if not (m_csrf and m_ad):
        raise RuntimeError("Failed to extract tokens from shrinkme gate page")

    csrf = m_csrf.group(1)
    ad_data = m_ad.group(1)
    m_fields = re.search(r'name="_Token\[fields\]"[^>]*value="([^"]+)"', r.text)
    m_unlocked = re.search(r'name="_Token\[unlocked\]"[^>]*value="([^"]+)"', r.text)

    m_counter = re.search(r'"counter_value":\s*"(\d+)"', r.text)
    counter = int(m_counter.group(1)) if m_counter else 12

    wait = max(0.1, counter - (time.time() - t0) + 0.5)
    notify(f"[shrink] respecting countdown timer ({wait:.1f}s)...")
    time.sleep(wait)

    s.cookies.set("ab", "2", domain="en.mrproblogger.com")

    payload = {
        "_method": "POST",
        "_csrfToken": csrf,
        "ad_form_data": ad_data,
    }
    if m_fields:
        payload["_Token[fields]"] = m_fields.group(1)
    if m_unlocked:
        payload["_Token[unlocked]"] = m_unlocked.group(1)

    r_post = s.post(
        "https://en.mrproblogger.com/links/go",
        data=payload,
        headers={
            "Origin": "https://en.mrproblogger.com",
            "Referer": f"https://en.mrproblogger.com/{slug}",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        timeout=25,
    )

    data = r_post.json() if r_post.text.strip().startswith("{") else {}
    if data.get("status") == "success" and data.get("url"):
        final_url = data["url"]
        notify(f"[shrink] destination resolved: {final_url[:70]}...")
        return final_url
    raise RuntimeError(f"Shrinkme links/go rejected: {r_post.text[:140]}")


def bypass_process(link, explicit_proxy=None, proxy_url=None, status_cb=None):
    def notify(msg):
        print(msg, flush=True)
        if status_cb:
            status_cb(msg)

    explicit_proxy = explicit_proxy or proxy_url
    family, short = normalize(link)
    if family is None:
        raise RuntimeError(f"unrecognized link (supported: vipshort, arolinks, vplink, easysky, monteolympus, shrinkme, dupload): {short[:60]}")

    chosen_proxy = None
    used_from_pool = False

    # ONLY USE PROXY FOR VIPSHORT!
    if family == "vipshort":
        if explicit_proxy:
            chosen_proxy = parse_proxy_any(explicit_proxy)
            notify(f"[vip] 🛡️ Using explicit proxy: {mask_proxy(chosen_proxy)}")
        else:
            pool_proxy = proxy_manager.get_random()
            if pool_proxy:
                chosen_proxy = pool_proxy
                used_from_pool = True
                notify(f"[vip] 🛡️ Selected proxy from pool ({proxy_manager.count()} total): {mask_proxy(chosen_proxy)}")
            elif os.environ.get("PROXY"):
                chosen_proxy = parse_proxy_any(os.environ.get("PROXY"))
                notify(f"[vip] 🛡️ Using env PROXY: {mask_proxy(chosen_proxy)}")
            else:
                notify("[vip] ℹ️ No proxies in pool — running direct...")
    else:
        # arolinks, vplink, easysky, monteolympus, shrinkme & dupload: STRICTLY DIRECT! No pool proxy is used!
        if explicit_proxy:
            chosen_proxy = parse_proxy_any(explicit_proxy)
            notify(f"[{family[:3]}] 🛡️ Using explicit proxy: {mask_proxy(chosen_proxy)}")
        else:
            chosen_proxy = None
            notify(f"[{family[:3]}] ⚡ Direct connection (proxy disabled for {family})")

    s, persona = build_session()
    if chosen_proxy:
        s.proxies = {"http": chosen_proxy, "https": chosen_proxy}

    notify(f"[*] routing: {family} ({persona})")

    try:
        if family == "vipshort":
            go_page = walk_vipshort(s, short, notify)
            notify(f"[vip] go page: {go_page[:70]}")
            r = s.get(go_page, timeout=25, headers={"Referer": BLOG})
            final = kill(s, go_page, r.text, host="m.vipshort.in", notify=notify)
            visit_final(s, final, "m.vipshort.in", notify)
        elif family == "dupload":
            final = bypass_dupload(s, short, notify)
        elif family == "vplink":
            go_page, html = walk_vplink(s, short, notify)
            final = kill_vplink(s, go_page, html, notify)
            visit_final(s, final, "vplink.in", notify)
        elif family == "easysky":
            final = bypass_easysky(s, short, notify)
            visit_final(s, final, "w.gameswow.info", notify)
        elif family == "monteolympus":
            final = bypass_monteolympus(s, short, notify)
            visit_final(s, final, "monteolympus.com", notify)
        elif family == "shrinkme":
            final = bypass_shrinkme(s, short, notify)
            visit_final(s, final, "en.mrproblogger.com", notify)
        else:
            go_page, html = walk_arolinks(s, short, notify)
            notify(f"[aro] go page: {go_page[:70]}")
            final = kill(s, go_page, html, host="arolinks.com", notify=notify)
            visit_final(s, final, "arolinks.com", notify)
        return final

    except Exception as e:
        # Auto-remove proxy if it failed on vipshort
        if family == "vipshort" and chosen_proxy and used_from_pool:
            proxy_manager.remove(chosen_proxy)
            notify(f"[vip] ⚠️ Proxy {mask_proxy(chosen_proxy)} failed. Auto-removed from pool! ({proxy_manager.count()} left)")
        raise


# ============================================================
# TELEGRAM LIVE UPDATER (Premium UI)
# ============================================================

SPINNERS = ["⏳", "⚙️", "🔄", "🛰️", "⚡"]

class TelegramLiveUpdater:
    def __init__(self, bot: telebot.TeleBot, chat_id: int, message_id: int, original_url: str, start_time: float):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.original_url = original_url
        self.start_time = start_time
        self.logs = []
        self.last_edit = 0.0
        self.spinner_idx = 0
        self.lock = threading.Lock()

    def update(self, line: str):
        with self.lock:
            self.logs.append(line)
            recent = self.logs[-5:]
            now = time.time()
            if now - self.last_edit >= 1.5:
                self.last_edit = now
                self.spinner_idx = (self.spinner_idx + 1) % len(SPINNERS)
                elapsed = time.perf_counter() - self.start_time
                self._send_edit("\n".join(recent), elapsed)

    def _send_edit(self, log_snippet: str, elapsed: float):
        icon = SPINNERS[self.spinner_idx]
        text = (
            f"╭━━━━〔 ⚡ <b>BYPASSING IN PROGRESS...</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Target Link:</b>\n"
            f"<code>{self.original_url}</code></blockquote>\n\n"
            f"📡 <b>Live Telemetry:</b>\n"
            f"<pre>{log_snippet}</pre>\n\n"
            f"╭─ 📊 <b>Status</b>\n"
            f"├ {icon} <b>Elapsed :</b> <code>{elapsed:.1f}s</code>\n"
            f"╰ 👨‍💻 <b>Developer:</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        try:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass

    def finish(self, final_url: str, elapsed: float):
        text = (
            f"╭━━━━〔 ⚡ <b>BYPASS SUCCESSFUL</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Original URL:</b>\n"
            f"<code>{self.original_url}</code></blockquote>\n\n"
            f"<blockquote>🎯 <b>Final Destination:</b>\n"
            f"<code>{final_url}</code></blockquote>\n\n"
            f"╭─ 📊 <b>Execution Details</b>\n"
            f"├ ⏱ <b>Time Taken :</b> <code>{elapsed:.2f}s</code>\n"
            f"├ 🛡 <b>Engine     :</b> <code>TLS Impersonation v2</code>\n"
            f"╰ 👨‍💻 <b>Developer  :</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        if final_url.startswith("http"):
            buttons.append(types.InlineKeyboardButton("🚀 Open Final Link", url=final_url))
        dev_handle = DEVELOPER.lstrip("@")
        buttons.append(types.InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{dev_handle}"))
        markup.add(*buttons)

        try:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception:
            try:
                self.bot.send_message(self.chat_id, text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass

    def error(self, err_msg: str, elapsed: float):
        text = (
            f"╭━━━━〔 ❌ <b>BYPASS FAILED</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Target Link:</b>\n"
            f"<code>{self.original_url}</code></blockquote>\n\n"
            f"<blockquote>⚠️ <b>Error Details:</b>\n"
            f"<code>{err_msg}</code></blockquote>\n\n"
            f"╭─ 📊 <b>Execution Details</b>\n"
            f"├ ⏱ <b>Time Taken :</b> <code>{elapsed:.2f}s</code>\n"
            f"╰ 👨‍💻 <b>Developer  :</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
            f"💡 <i>Tip: The link may be dead, or the shortener may require a proxy.</i>"
        )
        markup = types.InlineKeyboardMarkup()
        dev_handle = DEVELOPER.lstrip("@")
        markup.add(types.InlineKeyboardButton("👨‍💻 Contact Dev", url=f"https://t.me/{dev_handle}"))

        try:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception:
            try:
                self.bot.send_message(self.chat_id, text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass


# ============================================================
# CLOUD HEALTH CHECK SERVER (Railway / Web Service Support)
# ============================================================

def start_health_server():
    """Runs a tiny HTTP server on $PORT to satisfy Railway / cloud health checks."""
    port_str = os.environ.get("PORT")
    if not port_str:
        return

    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"MasterBypass Telegram Bot is healthy & running on Railway!")

        def log_message(self, format, *args):
            pass

    def serve():
        try:
            server = HTTPServer(("0.0.0.0", port), HealthHandler)
            print(f"[*] Cloud health server listening on port {port}", flush=True)
            server.serve_forever()
        except Exception as e:
            print(f"[!] Health server warning: {e}", flush=True)

    t = threading.Thread(target=serve, daemon=True)
    t.start()


# ============================================================
# TELEGRAM BOT CONTROLLER
# ============================================================

def setup_bot(token: str):
    bot = telebot.TeleBot(token, parse_mode=None, threaded=True)

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(msg):
        welcome = (
            f"╭━━━━〔 ⚡ <b>MASTER BYPASS BOT</b> 〕━━━━╮\n\n"
            f"🚀 <i>Instant Link Shortener Bypasser</i>\n"
            f"Skips countdown timers, gateway loops, and ads!\n\n"
            f"╭─ 💎 <b>Supported Networks</b>\n"
            f"├ 🌐 <code>arolinks.com</code> (multi-lap gateway — direct)\n"
            f"├ 🔗 <code>vipshort.in</code> (classic + search-hop — proxied)\n"
            f"├ ⚡ <code>vplink.in / vplinks.in</code> (multi-hop gateway — direct)\n"
            f"├ 🌌 <code>easysky.in / m.easysky.in</code> (instant SafeLink — direct)\n"
            f"├ 🏛️ <code>monteolympus.com</code> (instant 8-gate skip — direct)\n"
            f"├ 🎯 <code>shrinkme.click / io</code> (mrproblogger bypass — direct)\n"
            f"╰ 📦 <code>dupload.net / xyz</code> (direct CDN)\n\n"
            f"╭─ 🛡️ <b>Proxy Management</b>\n"
            f"├ ➕ <code>/addproxy &lt;proxy&gt;</code> - Check & add live proxy\n"
            f"├ 📁 <b>Send .txt file</b> - Fast threaded bulk scanner\n"
            f"├ 📊 <code>/proxies</code> - View active pool count\n"
            f"╰ 🗑️ <code>/clearproxies</code> - Reset proxy pool\n\n"
            f"╭─ 📖 <b>How to Use</b>\n"
            f"├ Send any link directly to this chat\n"
            f"╰ <i>Note: Proxies are used for vipshorts & auto-removed if dead!</i>\n\n"
            f"╭─ 👨‍💻 <b>Author</b>\n"
            f"╰ <b>Developer:</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        dev_handle = DEVELOPER.lstrip("@")
        markup.add(
            types.InlineKeyboardButton("👨‍💻 Developer Profile", url=f"https://t.me/{dev_handle}")
        )
        bot.reply_to(msg, welcome, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["addproxy"])
    def cmd_addproxy(msg):
        text = (msg.text or "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(
                msg,
                "⚠️ <b>Usage:</b>\n<code>/addproxy ip:port</code>\nor\n<code>/addproxy ip:port:user:pass</code>\nor\n<code>/addproxy http://user:pass@host:port</code>",
                parse_mode="HTML"
            )
            return

        raw_proxy = parts[1].strip()
        parsed = parse_proxy_any(raw_proxy)
        if not parsed:
            bot.reply_to(msg, "❌ <b>Invalid proxy format!</b>\nPlease provide a valid IP:Port or URL.", parse_mode="HTML")
            return

        masked = mask_proxy(parsed)
        status_msg = bot.reply_to(
            msg,
            f"╭━━━━〔 🔍 <b>ASYNC PROXY CHECK</b> 〕━━━━╮\n\n"
            f"<blockquote>🌐 <b>Proxy:</b>\n<code>{masked}</code></blockquote>\n\n"
            f"⏳ <i>Testing connectivity, latency & rotation async...</i>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯",
            parse_mode="HTML"
        )

        def check_worker():
            res = check_proxy_live(parsed, timeout=6)
            if res.get("live"):
                p_type = res.get("type", "Static")
                type_icon = "🔄" if p_type == "Rotating" else "⚡"
                latency_ms = int(res.get("latency", 0.0) * 1000)
                proxy_manager.add(
                    parsed,
                    p_type=p_type,
                    latency=res.get("latency", 0.0),
                    ip=res.get("ip", ""),
                    protocol=res.get("protocol", "HTTP")
                )
                stats = proxy_manager.get_stats()
                card = (
                    f"╭━━━━〔 ✅ <b>PROXY VERIFIED & ADDED</b> 〕━━━━╮\n\n"
                    f"<blockquote>🌐 <b>Proxy:</b>\n<code>{masked}</code></blockquote>\n\n"
                    f"╭─ 📊 <b>Diagnostic Analysis</b>\n"
                    f"├ 🏷 <b>Proxy Type  :</b> <code>{type_icon} {p_type}</code>\n"
                    f"├ 🛡 <b>Protocol    :</b> <code>{res.get('protocol', 'HTTP')}</code>\n"
                    f"├ ⚡ <b>Latency     :</b> <code>{latency_ms}ms</code>\n"
                    f"├ 📍 <b>Exit IP     :</b> <code>{res.get('ip', 'N/A')}</code>\n"
                    f"╰ 📦 <b>Active Pool :</b> <code>{stats['total']} ({stats['static']} Static, {stats['rotating']} Rotating)</code>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
                    f"🚀 <i>Added to vipshorts active proxy pool!</i>"
                )
            else:
                latency_ms = int(res.get("latency", 0.0) * 1000)
                card = (
                    f"╭━━━━〔 ❌ <b>PROXY DEAD / FAILED</b> 〕━━━━╮\n\n"
                    f"<blockquote>🌐 <b>Proxy:</b>\n<code>{masked}</code></blockquote>\n\n"
                    f"╭─ 📊 <b>Failure Report</b>\n"
                    f"├ ⚠️ <b>Reason   :</b> <code>{res.get('reason', 'Connection Failed')}</code>\n"
                    f"├ ⏱ <b>Timeout  :</b> <code>{latency_ms}ms</code>\n"
                    f"╰ 🚫 <b>Status   :</b> <code>Rejected (not added)</code>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
                    f"💡 <i>Tip: Check port, credentials, or IP authorization.</i>"
                )
            try:
                bot.edit_message_text(card, chat_id=msg.chat.id, message_id=status_msg.message_id, parse_mode="HTML")
            except Exception:
                bot.send_message(msg.chat.id, card, parse_mode="HTML")

        threading.Thread(target=check_worker, daemon=True).start()

    @bot.message_handler(commands=["proxies", "proxyinfo"])
    def cmd_proxies(msg):
        stats = proxy_manager.get_stats()
        card = (
            f"╭━━━━〔 🛡️ <b>PROXY POOL INVENTORY</b> 〕━━━━╮\n\n"
            f"╭─ 📊 <b>Live Pool Stats</b>\n"
            f"├ ⚡ <b>Static Dedicated :</b> <code>{stats['static']}</code>\n"
            f"├ 🔄 <b>Rotating Proxies :</b> <code>{stats['rotating']}</code>\n"
            f"├ 🎯 <b>Total Active     :</b> <code>{stats['total']} proxies</code>\n"
            f"╰ 🛡 <b>Assigned Service :</b> <code>vipshort.in</code> (auto-fallback)\n\n"
            f"╭─ 💡 <b>Management Commands</b>\n"
            f"├ ➕ <code>/addproxy &lt;proxy&gt;</code> - Test & add single proxy\n"
            f"├ 📁 <b>Send .txt file</b> - Fast async bulk scanner\n"
            f"╰ 🗑️ <code>/clearproxies</code> - Reset entire pool\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

    @bot.message_handler(commands=["clearproxies"])
    def cmd_clearproxies(msg):
        proxy_manager.clear()
        bot.reply_to(
            msg,
            "🗑️ <b>Proxy pool cleared!</b>\nAll proxies and metadata have been purged from storage.",
            parse_mode="HTML"
        )

    @bot.message_handler(content_types=["document"])
    def handle_document(msg):
        doc = msg.document
        if not doc:
            return
        fname = (doc.file_name or "").lower()
        if not (fname.endswith(".txt") or (doc.mime_type and "text" in doc.mime_type)):
            bot.reply_to(msg, "⚠️ Please send a <code>.txt</code> file containing proxies.", parse_mode="HTML")
            return

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded = bot.download_file(file_info.file_path)
            content = downloaded.decode("utf-8", errors="ignore")
        except Exception as e:
            bot.reply_to(msg, f"❌ Failed to download file: {e}")
            return

        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        valid_proxies = []
        for l in lines:
            p = parse_proxy_any(l)
            if p and p not in valid_proxies:
                valid_proxies.append(p)

        if not valid_proxies:
            bot.reply_to(msg, "❌ <b>No valid proxies found in this file!</b>\nEnsure lines contain <code>ip:port</code> or <code>ip:port:user:pass</code>.", parse_mode="HTML")
            return

        initial_card = (
            f"╭━━━━〔 ⚡ <b>ASYNC PROXY SCANNER</b> 〕━━━━╮\n\n"
            f"<blockquote>📄 <b>File:</b> <code>{doc.file_name}</code>\n"
            f"📊 <b>Total Extracted:</b> <code>{len(valid_proxies)} proxies</code>\n"
            f"⚡ <b>Concurrency:</b> <code>25 async workers</code></blockquote>\n\n"
            f"⏳ <i>Scanning proxies asynchronously, please wait...</i>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        status_msg = bot.reply_to(msg, initial_card, parse_mode="HTML")

        def scan_worker():
            def on_prog(stats_dict):
                tested = stats_dict["tested"]
                total = stats_dict["total"]
                pct = int((tested / total) * 100)
                bar = make_progress_bar(tested, total)
                avg_ms = int(stats_dict["avg_latency"] * 1000)

                text = (
                    f"╭━━━━〔 ⚡ <b>ASYNC PROXY SCANNER</b> 〕━━━━╮\n\n"
                    f"<blockquote>📄 <b>File:</b> <code>{doc.file_name}</code>\n"
                    f"📊 <b>Progress:</b> <code>{bar} {pct}% ({tested}/{total})</code></blockquote>\n\n"
                    f"╭─ 📈 <b>Live Statistics</b>\n"
                    f"├ ⚡ <b>Static Live   :</b> <code>{stats_dict['static']}</code>\n"
                    f"├ 🔄 <b>Rotating Live :</b> <code>{stats_dict['rotating']}</code>\n"
                    f"├ ❌ <b>Dead / Offline:</b> <code>{stats_dict['dead']}</code>\n"
                    f"├ ⏱ <b>Avg Latency   :</b> <code>{avg_ms}ms</code>\n"
                    f"╰ 📦 <b>Added to Pool :</b> <code>{stats_dict['live']}</code>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
                    f"⏳ <i>Scanning with 25 async workers...</i>"
                )
                try:
                    bot.edit_message_text(text, chat_id=msg.chat.id, message_id=status_msg.message_id, parse_mode="HTML")
                except Exception:
                    pass

            async def run_pipeline():
                return await async_scan_proxies_pipeline(valid_proxies, max_concurrency=25, on_progress=on_prog)

            live_results, dead_results = asyncio.run(run_pipeline())

            # Add live proxies with metadata
            for res in live_results:
                proxy_manager.add(
                    res["proxy"],
                    p_type=res.get("type", "Static"),
                    latency=res.get("latency", 0.0),
                    ip=res.get("ip", ""),
                    protocol=res.get("protocol", "HTTP")
                )

            # Autoremove dead proxies if they were previously in the pool
            pool = proxy_manager.get_all()
            for res in dead_results:
                p_dead = res["proxy"]
                if p_dead in pool:
                    proxy_manager.remove(p_dead)

            pool_stats = proxy_manager.get_stats()
            static_added = sum(1 for r in live_results if r.get("type") == "Static")
            rotating_added = len(live_results) - static_added
            avg_ms = int((sum(r.get("latency", 0.0) for r in live_results) / len(live_results)) * 1000) if live_results else 0

            final_card = (
                f"╭━━━━〔 🎯 <b>ASYNC SCAN COMPLETE</b> 〕━━━━╮\n\n"
                f"<blockquote>📄 <b>File:</b> <code>{doc.file_name}</code>\n"
                f"📊 <b>Total Processed:</b> <code>{len(valid_proxies)} proxies</code></blockquote>\n\n"
                f"╭─ 📊 <b>Scan Results Breakdown</b>\n"
                f"├ ⚡ <b>Static Live   :</b> <code>+{static_added} added</code>\n"
                f"├ 🔄 <b>Rotating Live :</b> <code>+{rotating_added} added</code>\n"
                f"├ ❌ <b>Dead Dropped  :</b> <code>{len(dead_results)} purged</code>\n"
                f"╰ ⏱ <b>Average Speed :</b> <code>{avg_ms}ms</code>\n\n"
                f"╭─ 📦 <b>Current Pool Inventory</b>\n"
                f"├ ⚡ <b>Static Active  :</b> <code>{pool_stats['static']}</code>\n"
                f"├ 🔄 <b>Rotating Active:</b> <code>{pool_stats['rotating']}</code>\n"
                f"╰ 🎯 <b>Total in Pool  :</b> <code>{pool_stats['total']} proxies</code>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
                f"🚀 <i>Live proxies are actively assigned to vipshorts!</i>"
            )
            try:
                bot.edit_message_text(final_card, chat_id=msg.chat.id, message_id=status_msg.message_id, parse_mode="HTML")
            except Exception:
                bot.send_message(msg.chat.id, final_card, parse_mode="HTML")

        threading.Thread(target=scan_worker, daemon=True).start()

    def handle_link_task(chat_id, user_msg_id, raw_url, proxy=None):
        start_time = time.perf_counter()
        initial_text = (
            f"╭━━━━〔 ⚡ <b>BYPASSING IN PROGRESS...</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Target Link:</b>\n"
            f"<code>{raw_url}</code></blockquote>\n\n"
            f"📡 <b>Live Telemetry:</b>\n"
            f"<pre>[*] Initializing TLS session & persona...</pre>\n\n"
            f"╭─ 📊 <b>Status</b>\n"
            f"├ ⏳ <b>Elapsed :</b> <code>0.0s</code>\n"
            f"╰ 👨‍💻 <b>Developer:</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        # Explicitly reply to the user's message
        status_msg = bot.send_message(
            chat_id,
            initial_text,
            reply_to_message_id=user_msg_id,
            parse_mode="HTML"
        )
        updater = TelegramLiveUpdater(bot, chat_id, status_msg.message_id, raw_url, start_time)

        try:
            final_link = bypass_process(raw_url, explicit_proxy=proxy, status_cb=updater.update)
            elapsed = time.perf_counter() - start_time
            updater.finish(final_link, elapsed)
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            updater.error(str(e), elapsed)

    @bot.message_handler(func=lambda m: True)
    def handle_all_messages(msg):
        text = (msg.text or "").strip()
        if not text or text.startswith("/"):
            return

        tokens = text.split()
        target_link = None
        custom_proxy = None

        for token in tokens:
            if any(d in token.lower() for d in ("http://", "https://", "arolinks.com", "vipshort.in", "vplink.in", "vplinks.in", "easysky.in", "monteolympus.com", "shrinkme.", "shrinke.me", "dupload")):
                target_link = token
                break

        if target_link and len(tokens) > 1:
            for token in tokens:
                if token != target_link and (":" in token or "@" in token):
                    custom_proxy = token
                    break

        if not target_link:
            if len(tokens) == 1 and len(tokens[0]) >= 4:
                target_link = tokens[0]
            else:
                bot.reply_to(
                    msg,
                    "⚠️ <b>Invalid Link!</b>\n\nPlease send a valid link (e.g. <code>https://arolinks.com/...</code>).",
                    parse_mode="HTML"
                )
                return

        threading.Thread(
            target=handle_link_task,
            args=(msg.chat.id, msg.message_id, target_link, custom_proxy),
            daemon=True
        ).start()

    return bot


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="MasterBypass Telegram Bot")
    parser.add_argument("link", nargs="?", default=None, help="Optional CLI test link")
    parser.add_argument("--token", default=None, help="Telegram Bot Token")
    parser.add_argument("--proxy", default=None, help="Optional proxy for CLI or Bot")
    args = parser.parse_args()

    # CLI direct test mode if link is provided
    if args.link:
        proxy_url = parse_proxy_any(args.proxy) if args.proxy else None
        print(f"[*] CLI Direct Bypass: {args.link}")
        start = time.perf_counter()
        try:
            final = bypass_process(args.link, proxy_url=proxy_url)
            elapsed = time.perf_counter() - start
            print(f"\nreal : {args.link}")
            print(f"developer : {DEVELOPER}")
            print(f"finallink : {final}")
            print(f"time : {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.perf_counter() - start
            print(f"\nFAIL: {e} ({elapsed:.2f}s)")
        return

    # Telegram Bot Mode
    token = args.token or BOT_TOKEN
    if not token:
        print("[!] ERROR: Telegram BOT_TOKEN is required!", file=sys.stderr)
        print("    Set it in your environment: export BOT_TOKEN='your_bot_token'", file=sys.stderr)
        print("    Or pass it via argument:   python bot.py --token 'your_bot_token'", file=sys.stderr)
        print("    On Railway: Add BOT_TOKEN in Environment Variables.", file=sys.stderr)
        sys.exit(1)

    # Start cloud health server on $PORT if assigned (Railway web service)
    start_health_server()

    bot = setup_bot(token)
    print(f"[*] MasterBypass Telegram Bot started successfully!")
    print(f"[*] Developer: {DEVELOPER}")
    print(f"[*] Listening for incoming messages...\n", flush=True)

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"[!] Polling restart due to error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
