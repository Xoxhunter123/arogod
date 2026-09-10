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

def parse_vipshort_slug(arg):
    arg = (arg or "").strip()
    m = re.search(r"(?:link\.|m\.)?vipshort\.in/([a-zA-Z0-9_-]+)", arg)
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]+$", arg):
        return arg
    return arg.rstrip("/").split("/")[-1].split("?")[0]


def resolve_vipshort_article_url(s, blog_base, myphp_html, notify):
    # Strategy 1: Fast URL slug generation from search query
    m_search = re.search(r'google\.com/search\?q=([^\s"\'<>]+)', myphp_html)
    if m_search:
        raw_q = unquote(m_search.group(1)).replace("+", " ")
        clean_title = re.sub(r'site:[^\s]+', '', raw_q, flags=re.I).strip()
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_title.lower()).strip('-')
        if slug:
            candidate = f"{blog_base.rstrip('/')}/{slug}/"
            return candidate
        return blog_base.rstrip("/") + "/"

    # Strategy 2: Blog homepage fallback
    notify("[vip] searching blog homepage for active ladder post...")
    try:
        r_home = s.get(blog_base, headers={"Referer": "https://www.google.com/"}, timeout=15)
        links = re.findall(r'href="(' + re.escape(blog_base.rstrip("/")) + r'/[a-z0-9-]+/)"', r_home.text)
        skip = ("about-us", "contact-us", "dmca", "privacy-policy", "category", "author", "feed", "wp-")
        valid_posts = [l for l in set(links) if not any(k in l for k in skip)]
        if valid_posts:
            return valid_posts[0]
    except Exception:
        pass

    return blog_base.rstrip("/") + "/"


def bypass_vipshort(s, input_arg, notify):
    slug = parse_vipshort_slug(input_arg)
    short_url = f"https://link.vipshort.in/{slug}"
    notify(f"[vip] target shortlink: {short_url}")

    headers_common = {
        "User-Agent": s.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": s.headers.get("Accept-Language", "en-US,en;q=0.9"),
    }

    # Step 1: Hop 1 - Get dynamic blog redirect
    notify(f"[vip] querying {short_url}...")
    r1 = s.get(short_url, headers=headers_common, allow_redirects=False, timeout=15)
    loc1 = r1.headers.get("location") or r1.headers.get("Location")

    if not loc1 and "m.vipshort.in" in r1.url:
        go_page = r1.url
        blog_base = "https://link.vipshort.in/"
        article_url = blog_base
    elif not loc1:
        raise RuntimeError(f"expected redirect from {short_url}, got status {r1.status_code}")
    else:
        if "href.li/?" in loc1:
            loc1 = loc1.split("href.li/?")[-1]

        parsed_loc = urlparse(loc1)
        blog_base = f"{parsed_loc.scheme}://{parsed_loc.netloc}/"
        notify(f"[vip] target blog: {blog_base}")

        # Step 2: Hop 2 - Visit myphp.php to register session cookies
        r_myphp = s.get(loc1, headers={**headers_common, "Referer": "https://link.vipshort.in/"}, timeout=15)

        # Step 3: Direct article resolution
        article_url = resolve_vipshort_article_url(s, blog_base, r_myphp.text, notify)
        notify(f"[vip] article target: {article_url}")

        # Step 4: Fast-path direct jump to vip1=4
        notify("[vip] fast-path: submitting vip1=4 directly...")
        r_lad = s.post(
            article_url,
            data={"vip1": "4", "g-recaptcha-response": ""},
            headers={
                **headers_common,
                "Origin": blog_base.rstrip("/"),
                "Referer": article_url,
            },
            timeout=15,
        )

        m_go = re.search(r'https://(?:m\.|link\.)?vipshort\.in/[^\s"\'<>]+', r_lad.text)
        if m_go:
            go_page = m_go.group(0)
            notify(f"[vip] ladder bypassed instantly! go page: {go_page[:60]}...")
        else:
            notify("[vip] direct jump unfulfilled, stepping ladder (vip1: 2 -> 3 -> 4)...")
            current_vip = "2"
            go_page = None
            for _ in range(4):
                time.sleep(1.0)
                r_step = s.post(
                    article_url,
                    data={"vip1": current_vip, "g-recaptcha-response": ""},
                    headers={**headers_common, "Origin": blog_base.rstrip("/"), "Referer": article_url},
                    timeout=15,
                )
                m = re.search(r'https://(?:m\.|link\.)?vipshort\.in/[^\s"\'<>]+', r_step.text)
                if m:
                    go_page = m.group(0)
                    break
                m_next = re.search(r'name="vip1"\s+value="([^"]+)"', r_step.text)
                current_vip = m_next.group(1) if m_next else str(int(current_vip) + 1)

            if not go_page:
                raise RuntimeError("failed to obtain go-page URL from blog ladder")

    # Step 5: Load go page on m.vipshort.in & harvest form
    notify("[vip] fetching adLinkFly form...")
    r_go = s.get(go_page, headers={**headers_common, "Referer": article_url}, timeout=15)

    inputs = {}
    for tag in re.finditer(r'<input[^>]+>', r_go.text):
        t = tag.group(0)
        n = re.search(r'name="([^"]+)"', t)
        v = re.search(r'value="([^"]*)"', t)
        if n:
            inputs[n.group(1)] = v.group(1) if v else ""

    if "ad_form_data" not in inputs:
        raise RuntimeError("go page layout missing ad_form_data token")

    target_host = "m.vipshort.in"
    s.cookies.set("ab", "2", domain=target_host)
    if inputs.get("_csrfToken"):
        s.cookies.set("csrfToken", inputs["_csrfToken"], domain=target_host)

    m_counter = re.search(r'"counter_value":\s*"(\d+)"', r_go.text)
    counter = int(m_counter.group(1)) if m_counter else 5
    wait_time = counter + 0.8

    notify(f"[vip] waiting countdown timer: {wait_time:.1f}s...")
    time.sleep(wait_time)

    # Step 6: Post /links/go
    payload = dict(inputs)
    payload["_method"] = "POST"

    post_headers = {
        "Origin": f"https://{target_host}",
        "Referer": go_page,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    notify("[vip] submitting final kill shot to /links/go...")
    r_kill = s.post(
        f"https://{target_host}/links/go",
        data=payload,
        headers=post_headers,
        timeout=15,
    )

    try:
        res = r_kill.json()
    except Exception:
        raise RuntimeError(f"non-JSON response from links/go: {r_kill.text[:140]}")

    if res.get("status") == "success" and res.get("url"):
        final_dest = res["url"]
        notify(f"[vip] destination resolved: {final_dest[:70]}...")
        return final_dest
    else:
        raise RuntimeError(f"bypass failed: {r_kill.text[:140]}")


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
                raise RuntimeError("Cloudflare challenge encountered on datacenter IP.")

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
    raise RuntimeError("walk ran out of hops — link expired or unreachable")


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


def bypass_process(link, status_cb=None):
    def notify(msg):
        print(msg, flush=True)
        if status_cb:
            status_cb(msg)

    family, short = normalize(link)
    if family is None:
        raise RuntimeError(f"unrecognized link (supported: vipshort, arolinks, vplink, easysky, monteolympus, shrinkme, dupload): {short[:60]}")

    s, persona = build_session()
    notify(f"[*] routing: {family} ({persona}) [direct]")

    if family == "vipshort":
        final = bypass_vipshort(s, short, notify)
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
            f"💡 <i>Tip: The link may be expired, dead, or invalid.</i>"
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
            f"├ 🔗 <code>vipshort.in</code> (ultra-fast blog ladder — direct)\n"
            f"├ ⚡ <code>vplink.in / vplinks.in</code> (multi-hop gateway — direct)\n"
            f"├ 🌌 <code>easysky.in / m.easysky.in</code> (instant SafeLink — direct)\n"
            f"├ 🏛️ <code>monteolympus.com</code> (instant 8-gate skip — direct)\n"
            f"├ 🎯 <code>shrinkme.click / io</code> (mrproblogger bypass — direct)\n"
            f"╰ 📦 <code>dupload.net / xyz</code> (direct CDN)\n\n"
            f"╭─ 📖 <b>How to Use</b>\n"
            f"├ Send any supported link directly to this chat\n"
            f"╰ <i>Fast pure direct bypass with real-time progress!</i>\n\n"
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

    def handle_link_task(chat_id, user_msg_id, raw_url):
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
            final_link = bypass_process(raw_url, status_cb=updater.update)
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

        for token in tokens:
            if any(d in token.lower() for d in ("http://", "https://", "arolinks.com", "vipshort.in", "vplink.in", "vplinks.in", "easysky.in", "monteolympus.com", "shrinkme.", "shrinke.me", "dupload")):
                target_link = token
                break

        if not target_link:
            if len(tokens) == 1 and len(tokens[0]) >= 4:
                target_link = tokens[0]
            else:
                bot.reply_to(
                    msg,
                    "⚠️ <b>Invalid Link!</b>\n\nPlease send a valid link (e.g. <code>https://link.vipshort.in/...</code>).",
                    parse_mode="HTML"
                )
                return

        threading.Thread(
            target=handle_link_task,
            args=(msg.chat.id, msg.message_id, target_link),
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
    args = parser.parse_args()

    # CLI direct test mode if link is provided
    if args.link:
        print(f"[*] CLI Direct Bypass: {args.link}")
        start = time.perf_counter()
        try:
            final = bypass_process(args.link)
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
