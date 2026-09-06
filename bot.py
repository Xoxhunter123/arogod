#!/usr/bin/env python3
"""
bot.py — Telegram Bot & Link Bypass Engine
Supports:
  • vipshort.in (classic funnel + search-hop variant)
  • arolinks.com (multi-lap gateway countdowns)
  • dupload.net / dupload.xyz (direct CDN unwrap)

Render Hosting:
  Runs on Render as Web Service (built-in $PORT health server) or Background Worker.
"""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import random
import re
import sys
import threading
import time
from urllib.parse import quote, unquote, urljoin

from curl_cffi import requests as cr
import telebot
from telebot import types

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


def normalize(link):
    u = (link or "").strip()
    if not u:
        return None, None
    m = re.match(r"https?://(?:link\.|m\.)?vipshort\.in/(.+?)/?$", u)
    if m:
        return "vipshort", f"https://link.vipshort.in/{m.group(1)}"
    m = re.match(r"https?://(?:www\.)?arolinks\.com/(.+?)/?$", u)
    if m:
        return "arolinks", f"https://arolinks.com/{m.group(1)}"
    m = re.match(r"https?://(?:www\.)?dupload\.(?:net|xyz)/(.+?)/?$", u)
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
                notify(f"[aro] ⚠️ Cloudflare Challenge on Render IP (HTTP {r.status_code})")
                raise RuntimeError("Cloudflare blocked Render's datacenter IP. Set 'PROXY' in Render Environment Variables or send '<url> <proxy>'.")

            # Check for fallback click here anchor
            anchor_m = re.search(r'<a[^>]+href=[\'"](https?://[^\'"]+)[\'"][^>]*>\s*(?:click here|open link|continue)', r.text, re.I)
            if anchor_m and "arolinks.com" not in anchor_m.group(1):
                url = anchor_m.group(1).strip()
                time.sleep(random.uniform(0.9, 2.2))
                continue

            notify(f"[aro] ⚠️ arolinks returned no redirect (HTTP {r.status_code}). IP blocked on Render.")
            raise RuntimeError("arolinks IP blocked on Render. Add a PROXY in Render Environment Variables or send with proxy.")

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


def bypass_process(link, proxy_url=None, status_cb=None):
    def notify(msg):
        print(msg, flush=True)
        if status_cb:
            status_cb(msg)

    s, persona = build_session()
    if proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}

    family, short = normalize(link)
    if family is None:
        raise RuntimeError(f"unrecognized link (not vipshort/arolinks): {short[:60]}")

    notify(f"[*] routing: {family} ({persona})")

    if family == "vipshort":
        go_page = walk_vipshort(s, short, notify)
        notify(f"[vip] go page: {go_page[:70]}")
        r = s.get(go_page, timeout=25, headers={"Referer": BLOG})
        final = kill(s, go_page, r.text, host="m.vipshort.in", notify=notify)
        visit_final(s, final, "m.vipshort.in", notify)
    elif family == "dupload":
        final = bypass_dupload(s, short, notify)
    else:
        go_page, html = walk_arolinks(s, short, notify)
        notify(f"[aro] go page: {go_page[:70]}")
        final = kill(s, go_page, html, host="arolinks.com", notify=notify)
        visit_final(s, final, "arolinks.com", notify)

    return final


# ============================================================
# TELEGRAM LIVE UPDATER
# ============================================================

class TelegramLiveUpdater:
    def __init__(self, bot: telebot.TeleBot, chat_id: int, message_id: int, original_url: str):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.original_url = original_url
        self.logs = []
        self.last_edit = 0.0
        self.lock = threading.Lock()

    def update(self, line: str):
        with self.lock:
            self.logs.append(line)
            recent = self.logs[-5:]
            now = time.time()
            if now - self.last_edit >= 1.6:
                self.last_edit = now
                self._send_edit("\n".join(recent))

    def _send_edit(self, log_snippet: str):
        text = (
            f"⚡ <b>Bypassing Link...</b>\n"
            f"🔗 <code>{self.original_url}</code>\n\n"
            f"<b>Terminal Progress:</b>\n"
            f"<pre>{log_snippet}</pre>"
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
            f"real : {self.original_url}\n"
            f"developer : {DEVELOPER}\n"
            f"finallink : {final_url}\n"
            f"time : {elapsed:.2f}s"
        )
        markup = types.InlineKeyboardMarkup()
        if final_url.startswith("http"):
            markup.add(types.InlineKeyboardButton("🔗 Open Final Link", url=final_url))
        try:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
                reply_markup=markup
            )
        except Exception:
            try:
                self.bot.send_message(self.chat_id, text, reply_markup=markup)
            except Exception:
                pass

    def error(self, err_msg: str, elapsed: float):
        text = (
            f"❌ <b>Bypass Failed</b>\n\n"
            f"real : {self.original_url}\n"
            f"developer : {DEVELOPER}\n"
            f"error : {err_msg}\n"
            f"time : {elapsed:.2f}s"
        )
        try:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
                parse_mode="HTML"
            )
        except Exception:
            try:
                self.bot.send_message(self.chat_id, text, parse_mode="HTML")
            except Exception:
                pass


# ============================================================
# CLOUD HEALTH CHECK SERVER (Railway / Web Service Support)
# ============================================================

def start_health_server():
    """Runs a tiny HTTP server on $PORT to satisfy Railway / cloud health checks."""
    port_str = os.environ.get("PORT")
    if not port_str:
        return  # If running in local or pure worker mode without $PORT, skip

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
            f"👋 <b>Welcome to MasterBypass Bot!</b>\n\n"
            f"Send me any link from:\n"
            f"• <code>arolinks.com</code>\n"
            f"• <code>link.vipshort.in</code> (or bare slug)\n"
            f"• <code>dupload.net / dupload.xyz</code>\n\n"
            f"⚡ <i>I will bypass it and show live terminal progress!</i>\n\n"
            f"👨‍💻 Developer: <b>{DEVELOPER}</b>"
        )
        bot.reply_to(msg, welcome, parse_mode="HTML")

    def handle_link_task(chat_id, raw_url, proxy=None):
        start_time = time.perf_counter()
        initial_text = (
            f"⚡ <b>Bypassing Link...</b>\n"
            f"🔗 <code>{raw_url}</code>\n\n"
            f"<b>Terminal Progress:</b>\n"
            f"<pre>[*] Initializing TLS session...</pre>"
        )
        status_msg = bot.send_message(chat_id, initial_text, parse_mode="HTML")
        updater = TelegramLiveUpdater(bot, chat_id, status_msg.message_id, raw_url)

        # Proxy fallback: explicitly passed, or PROXY env var
        chosen_proxy = proxy or os.environ.get("PROXY", "").strip() or None
        if chosen_proxy:
            chosen_proxy = parse_proxy_any(chosen_proxy)

        try:
            final_link = bypass_process(raw_url, proxy_url=chosen_proxy, status_cb=updater.update)
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

        # Extract URL or slug
        tokens = text.split()
        target_link = None
        custom_proxy = None

        for token in tokens:
            if "http://" in token or "https://" in token or "arolinks.com" in token or "vipshort.in" in token:
                target_link = token
                break

        # Check for proxy token
        if target_link and len(tokens) > 1:
            for token in tokens:
                if token != target_link and (":" in token or "@" in token):
                    custom_proxy = token
                    break

        if not target_link:
            # Fallback: if it's a single word with no spaces, treat as slug
            if len(tokens) == 1 and len(tokens[0]) >= 4:
                target_link = tokens[0]
            else:
                bot.reply_to(msg, "⚠️ Please send a valid link (e.g. <code>https://arolinks.com/...</code>)", parse_mode="HTML")
                return

        # Run bypass in background thread to never block telegram polling
        threading.Thread(
            target=handle_link_task,
            args=(msg.chat.id, target_link, custom_proxy),
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
        print("    On Render: Add BOT_TOKEN in Environment Variables.", file=sys.stderr)
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
