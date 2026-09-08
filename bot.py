import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import random
import re
import secrets
import sys
import threading
import time
from urllib.parse import quote, unquote, urljoin, urlparse, parse_qs

from curl_cffi import requests as cr
from curl_cffi.requests import AsyncSession
import logging
import telebot
from telebot import types, apihelper

# Enable telebot middleware support before any TeleBot instance is initialized
apihelper.ENABLE_MIDDLEWARE = True

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

# Configure root logger to output to stdout so Railway/cloud displays all bot events and errors
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
telebot.logger.setLevel(logging.INFO)
# Explicitly attach stdout handler to telebot.logger so telebot internal errors are visible in cloud logs
_tb_stdout = logging.StreamHandler(sys.stdout)
_tb_stdout.setLevel(logging.INFO)
_tb_stdout.setFormatter(logging.Formatter("%(asctime)s [TeleBot] [%(levelname)s] %(message)s"))
telebot.logger.handlers = [_tb_stdout]

# ============================================================
# CONFIGURATION
# ============================================================

def safe_int_env(key: str, default: int) -> int:
    val = (os.environ.get(key) or "").strip().strip("\"'")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        print(f"[!] Warning: Invalid integer for env {key}='{val}', using default {default}", flush=True)
        return default

DEVELOPER = os.environ.get("DEVELOPER", "@xoxhunterxd").strip().strip("\"'")
OWNER_ID = safe_int_env("OWNER_ID", 6021047784)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip().strip("\"'")
FORCE_CHANNEL_ID = safe_int_env("FORCE_CHANNEL_ID", -1003902238678)
FORCE_CHANNEL_LINK = os.environ.get("FORCE_CHANNEL_LINK", "https://t.me/+9tlFEYFTyG1jODE1").strip().strip("\"'")
LOG_CHANNEL_ID = safe_int_env("LOG_CHANNEL_ID", -1004150412297)

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


def make_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "[░░░░░░░░░░]"
    filled = max(0, min(length, int(length * (current / total))))
    return f"[{'█' * filled}{'░' * (length - filled)}]"


def parse_duration_string(s: str) -> int:
    """Parses duration strings like 10m, 1h, 6h, 24h, 7d, 30d to integer seconds."""
    s = str(s).strip().lower()
    if s.endswith("s"):
        return int(s[:-1])
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("d"):
        return int(s[:-1]) * 86400
    elif s.endswith("w"):
        return int(s[:-1]) * 604800
    return int(s)


# ============================================================
# USER MANAGER V3 (Atomic Persistence, Referrals, Credits, Keys)
# ============================================================

class UserManager:
    """Thread-safe persistent user manager with atomic JSON writes, referral program, credits, and key redemption."""
    def __init__(self, db_path="users.json"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.all_users = set()
        self.user_profiles = {}
        self.approved = {}
        self.redeem_keys = {}
        self.daily_usage = {}
        self.shortener_stats = {
            "arolinks": 0,
            "vipshort": 0,
            "vplink": 0,
            "easysky": 0,
            "monteolympus": 0,
            "shrinkme": 0,
            "dupload": 0,
        }
        self.load()

    def load(self):
        with self.lock:
            if os.path.isfile(self.db_path):
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.all_users = set(data.get("all_users", []))
                        self.user_profiles = data.get("user_profiles", {})
                        self.approved = data.get("approved", {})
                        self.redeem_keys = data.get("redeem_keys", {})
                        self.daily_usage = data.get("daily_usage", {})
                        stats = data.get("shortener_stats", {})
                        for k, v in stats.items():
                            self.shortener_stats[k] = v
                except Exception as e:
                    print(f"[!] Error loading {self.db_path}: {e}", flush=True)
            self.all_users.add(OWNER_ID)

    def save(self):
        """Atomic crash-safe file persistence to prevent loss across redeploys."""
        with self.lock:
            try:
                data = {
                    "all_users": list(self.all_users),
                    "user_profiles": self.user_profiles,
                    "approved": self.approved,
                    "redeem_keys": self.redeem_keys,
                    "daily_usage": self.daily_usage,
                    "shortener_stats": self.shortener_stats,
                }
                tmp_path = f"{self.db_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.db_path)
            except Exception as e:
                print(f"[!] Error saving {self.db_path}: {e}", flush=True)

    def register(self, user_id: int, username: str = None, pending_ref: int = None):
        uid_str = str(user_id)
        with self.lock:
            self.all_users.add(user_id)
            if uid_str not in self.user_profiles:
                self.user_profiles[uid_str] = {
                    "username": username or "N/A",
                    "credits": 0,
                    "referred_by": None,
                    "referrals": [],
                    "referral_count": 0,
                    "pending_referrer": pending_ref if (pending_ref and pending_ref != user_id) else None,
                    "joined_channel": False,
                }
            else:
                if username:
                    self.user_profiles[uid_str]["username"] = username
        self.save()

    def confirm_channel_joined(self, user_id: int) -> tuple[bool, int, bool]:
        """
        Confirms channel membership. If user had a pending referral,
        credits it to the referrer.
        Every 5 referrals unlocks 6 hours of unlimited VIP access!
        Returns: (is_confirmed_ref, referrer_id, unlocked_milestone)
        """
        uid_str = str(user_id)
        with self.lock:
            prof = self.user_profiles.get(uid_str, {})
            pending_ref = prof.get("pending_referrer")
            if not pending_ref:
                prof["joined_channel"] = True
                self.user_profiles[uid_str] = prof
                self.save()
                return False, None, False

            ref_str = str(pending_ref)
            prof["referred_by"] = pending_ref
            prof["pending_referrer"] = None
            prof["joined_channel"] = True
            self.user_profiles[uid_str] = prof

            ref_prof = self.user_profiles.setdefault(ref_str, {
                "username": "N/A", "credits": 0, "referrals": [], "referral_count": 0
            })
            if user_id not in ref_prof.get("referrals", []):
                ref_prof.setdefault("referrals", []).append(user_id)
                ref_prof["referral_count"] = ref_prof.get("referral_count", 0) + 1

            count = ref_prof["referral_count"]
            unlocked = (count % 5 == 0)
            self.user_profiles[ref_str] = ref_prof

        if unlocked:
            self.add_time(pending_ref, seconds=6 * 3600)

        self.save()
        return True, pending_ref, unlocked

    def is_owner(self, user_id: int) -> bool:
        return int(user_id) == OWNER_ID

    def is_approved(self, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        uid_str = str(user_id)
        with self.lock:
            if uid_str in self.approved:
                exp = self.approved[uid_str].get("expires_at", 0)
                if exp > time.time():
                    return True
                else:
                    del self.approved[uid_str]
                    self.save()
        return False

    def add_time(self, user_id: int, seconds: int, username: str = None) -> float:
        """Adds arbitrary duration (hours or days) to VIP access."""
        uid_str = str(user_id)
        with self.lock:
            self.all_users.add(user_id)
            current_exp = self.approved.get(uid_str, {}).get("expires_at", 0)
            base_time = max(current_exp, time.time())
            new_exp = base_time + seconds
            self.approved[uid_str] = {
                "expires_at": new_exp,
                "added_at": time.time(),
                "seconds": seconds,
                "username": username or self.approved.get(uid_str, {}).get("username", "N/A"),
            }
        self.save()
        return new_exp

    def add_approved(self, user_id: int, days: int, username: str = None) -> float:
        return self.add_time(user_id, days * 86400, username)

    def remove_approved(self, user_id: int) -> bool:
        uid_str = str(user_id)
        with self.lock:
            if uid_str in self.approved:
                del self.approved[uid_str]
                self.save()
                return True
            return False

    def get_credits(self, user_id: int) -> int:
        uid_str = str(user_id)
        now = time.time()
        with self.lock:
            prof = self.user_profiles.get(uid_str, {})
            batches = prof.get("credit_batches")
            if batches is None:
                old_c = prof.get("credits", 0)
                batches = [{"amount": old_c, "expires_at": None}] if old_c > 0 else []

            # Purge expired batches
            valid_batches = [
                b for b in batches
                if (b.get("expires_at") is None or b.get("expires_at") > now) and b.get("amount", 0) > 0
            ]
            prof["credit_batches"] = valid_batches
            prof["credits"] = sum(b["amount"] for b in valid_batches)
            self.user_profiles[uid_str] = prof
            return prof["credits"]

    def get_credit_summary(self, user_id: int) -> tuple[int, list]:
        """Returns total valid credits and list of active expiring batches."""
        uid_str = str(user_id)
        now = time.time()
        with self.lock:
            prof = self.user_profiles.get(uid_str, {})
            batches = prof.get("credit_batches")
            if batches is None:
                old_c = prof.get("credits", 0)
                batches = [{"amount": old_c, "expires_at": None}] if old_c > 0 else []

            valid_batches = [
                b for b in batches
                if (b.get("expires_at") is None or b.get("expires_at") > now) and b.get("amount", 0) > 0
            ]
            prof["credit_batches"] = valid_batches
            prof["credits"] = sum(b["amount"] for b in valid_batches)
            self.user_profiles[uid_str] = prof
            total = prof["credits"]
            expiring = [b for b in valid_batches if b.get("expires_at")]
            return total, expiring

    def add_credits(self, user_id: int, amount: int, duration_seconds: int = None) -> int:
        uid_str = str(user_id)
        now = time.time()
        exp = (now + duration_seconds) if duration_seconds else None
        with self.lock:
            self.all_users.add(user_id)
            prof = self.user_profiles.setdefault(uid_str, {
                "username": "N/A", "credits": 0, "referred_by": None,
                "referrals": [], "referral_count": 0, "pending_referrer": None, "joined_channel": False
            })
            batches = prof.get("credit_batches")
            if batches is None:
                old_c = prof.get("credits", 0)
                batches = [{"amount": old_c, "expires_at": None}] if old_c > 0 else []

            valid_batches = [
                b for b in batches
                if (b.get("expires_at") is None or b.get("expires_at") > now) and b.get("amount", 0) > 0
            ]
            valid_batches.append({"amount": max(0, amount), "expires_at": exp})
            prof["credit_batches"] = valid_batches
            prof["credits"] = sum(b["amount"] for b in valid_batches)
            self.user_profiles[uid_str] = prof
            new_bal = prof["credits"]
        self.save()
        return new_bal

    def deduct_credits(self, user_id: int, amount: int) -> int:
        uid_str = str(user_id)
        now = time.time()
        with self.lock:
            self.all_users.add(user_id)
            prof = self.user_profiles.setdefault(uid_str, {
                "username": "N/A", "credits": 0, "referred_by": None,
                "referrals": [], "referral_count": 0, "pending_referrer": None, "joined_channel": False
            })
            batches = prof.get("credit_batches")
            if batches is None:
                old_c = prof.get("credits", 0)
                batches = [{"amount": old_c, "expires_at": None}] if old_c > 0 else []

            valid_batches = [
                b for b in batches
                if (b.get("expires_at") is None or b.get("expires_at") > now) and b.get("amount", 0) > 0
            ]
            # Prioritize spending credits that expire soonest; permanent credits (None) spent last
            valid_batches.sort(key=lambda b: b.get("expires_at") if b.get("expires_at") is not None else float("inf"))

            to_deduct = max(0, amount)
            new_batches = []
            for b in valid_batches:
                if to_deduct <= 0:
                    new_batches.append(b)
                elif b["amount"] <= to_deduct:
                    to_deduct -= b["amount"]
                else:
                    b["amount"] -= to_deduct
                    to_deduct = 0
                    new_batches.append(b)

            prof["credit_batches"] = new_batches
            prof["credits"] = sum(b["amount"] for b in new_batches)
            self.user_profiles[uid_str] = prof
            new_bal = prof["credits"]
        self.save()
        return new_bal

    def create_key(self, key_type: str, val_str: str, max_uses: int = 1, key_expiry_secs: int = None, credit_duration_secs: int = None) -> tuple[bool, str, str]:
        key_type = key_type.lower().strip()
        code_rand = secrets.token_hex(3).upper()
        now = time.time()
        k_exp = (now + key_expiry_secs) if key_expiry_secs else None

        if key_type == "time":
            v = val_str.lower().strip()
            if v.endswith("h"):
                hours = int(v[:-1])
                secs = hours * 3600
                desc = f"{hours} Hours VIP"
            elif v.endswith("d"):
                days = int(v[:-1])
                secs = days * 86400
                desc = f"{days} Days VIP"
            else:
                hours = int(v)
                secs = hours * 3600
                desc = f"{hours} Hours VIP"
            code = f"VIP-TIME-{val_str.upper()}-{code_rand}"
            with self.lock:
                self.redeem_keys[code] = {
                    "code": code,
                    "type": "time",
                    "value": val_str,
                    "seconds": secs,
                    "max_uses": max(1, max_uses),
                    "redeemed_by": [],
                    "key_expires_at": k_exp,
                    "credit_duration": None,
                    "created_at": now,
                    "used": False,
                }
            self.save()
            return True, code, desc

        elif key_type == "credit":
            amount = int(val_str)
            dur_label = ""
            if credit_duration_secs:
                if credit_duration_secs >= 86400:
                    dur_label = f" (valid {credit_duration_secs // 86400}d)"
                elif credit_duration_secs >= 3600:
                    dur_label = f" (valid {credit_duration_secs // 3600}h)"
                else:
                    dur_label = f" (valid {credit_duration_secs // 60}m)"
            desc = f"{amount} Credits{dur_label}"
            code = f"VIP-CRED-{amount}-{code_rand}"
            with self.lock:
                self.redeem_keys[code] = {
                    "code": code,
                    "type": "credit",
                    "value": amount,
                    "amount": amount,
                    "max_uses": max(1, max_uses),
                    "redeemed_by": [],
                    "key_expires_at": k_exp,
                    "credit_duration": credit_duration_secs,
                    "created_at": now,
                    "used": False,
                }
            self.save()
            return True, code, desc

        return False, "", "Invalid type"

    def create_batch_keys(self, count: int, key_type: str, val_str: str, max_uses: int = 1, key_expiry_secs: int = None, credit_duration_secs: int = None) -> list[tuple[str, str]]:
        generated = []
        for _ in range(max(1, count)):
            ok, code, desc = self.create_key(key_type, val_str, max_uses=max_uses, key_expiry_secs=key_expiry_secs, credit_duration_secs=credit_duration_secs)
            if ok:
                generated.append((code, desc))
        return generated

    def redeem_key(self, user_id: int, code: str) -> tuple[bool, str, dict]:
        code = code.strip().upper()
        now = time.time()
        with self.lock:
            if code not in self.redeem_keys:
                return False, "❌ <b>Invalid Key Code!</b> Please check and try again.", None
            k = self.redeem_keys[code]

            # Normalize older keys without redeemed_by
            if "redeemed_by" not in k:
                k["redeemed_by"] = [k["used_by"]] if k.get("used_by") else []
            if "max_uses" not in k:
                k["max_uses"] = 1

            # Check key expiry
            k_exp = k.get("key_expires_at")
            if k_exp and now > k_exp:
                exp_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(k_exp))
                return False, f"❌ <b>Key Expired!</b> This redeem key expired on <code>{exp_str}</code>.", None

            # Check if this user already redeemed this key
            if user_id in k["redeemed_by"]:
                return False, "❌ <b>Already Redeemed!</b> You have already claimed this key.", None

            # Check max usage
            if len(k["redeemed_by"]) >= k.get("max_uses", 1):
                return False, "❌ <b>Key Fully Claimed!</b> This key has reached its maximum user limit.", None

            # Record redemption for this user
            k["redeemed_by"].append(user_id)
            if len(k["redeemed_by"]) >= k.get("max_uses", 1):
                k["used"] = True
            k["used_by"] = user_id
            k["used_at"] = now
            self.redeem_keys[code] = k

        if k["type"] == "time":
            new_exp = self.add_time(user_id, k["seconds"])
            exp_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(new_exp))
            self.save()
            uses_left = k.get("max_uses", 1) - len(k["redeemed_by"])
            left_info = f"\n👥 <i>Remaining user claims for this key: {uses_left}</i>" if k.get("max_uses", 1) > 1 else ""
            return True, f"🎉 <b>VIP Key Redeemed Successfully!</b>\nGranted <b>{k['value']}</b> of Unlimited VIP Access!\n📅 Valid until: <code>{exp_str}</code>{left_info}", k

        elif k["type"] == "credit":
            c_dur = k.get("credit_duration")
            new_bal = self.add_credits(user_id, k["amount"], duration_seconds=c_dur)
            self.save()
            dur_info = ""
            if c_dur:
                exp_time_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now + c_dur))
                dur_info = f"\n⏳ <i>Notice: These credits expire on <code>{exp_time_str}</code>!</i>"
            uses_left = k.get("max_uses", 1) - len(k["redeemed_by"])
            left_info = f"\n👥 <i>Remaining user claims for this key: {uses_left}</i>" if k.get("max_uses", 1) > 1 else ""
            return True, f"🎉 <b>Credit Key Redeemed Successfully!</b>\nAdded <b>+{k['amount']} Credits</b> to your account!\n💰 New Balance: <b>{new_bal} Credits</b>{dur_info}{left_info}", k

        return False, "Unknown key type", None

    def find_available_keys_in_text(self, user_id: int, text: str) -> list[str]:
        """Extracts candidate VIP keys from text and returns those that user can redeem."""
        candidates = re.findall(r"VIP-(?:TIME|CRED)-[A-Za-z0-9\-]+", text, re.I)
        now = time.time()
        available = []
        with self.lock:
            for c in candidates:
                c_up = c.upper()
                if c_up in self.redeem_keys:
                    k = self.redeem_keys[c_up]
                    red_by = k.get("redeemed_by")
                    if red_by is None:
                        red_by = [k["used_by"]] if k.get("used_by") else []
                    max_u = k.get("max_uses", 1)
                    k_exp = k.get("key_expires_at")
                    if k_exp and now > k_exp:
                        continue
                    if user_id in red_by:
                        continue
                    if len(red_by) >= max_u:
                        continue
                    available.append(c_up)
        return available

    def list_active_keys(self) -> list:
        now = time.time()
        with self.lock:
            active = []
            for k in self.redeem_keys.values():
                red_by = k.get("redeemed_by")
                if red_by is None:
                    red_by = [k["used_by"]] if k.get("used_by") else []
                max_u = k.get("max_uses", 1)
                k_exp = k.get("key_expires_at")
                if k_exp and now > k_exp:
                    continue
                if len(red_by) < max_u:
                    active.append(k)
            return active

    def get_user_status(self, user_id: int) -> dict:
        uid_str = str(user_id)
        credits = self.get_credits(user_id)
        with self.lock:
            prof = self.user_profiles.get(uid_str, {})
            ref_count = prof.get("referral_count", 0)
        cycle = ref_count % 5
        needed = 5 - cycle

        if self.is_owner(user_id):
            return {
                "role": "owner", "unlimited": True, "expires_at": None,
                "days_left": 999999, "hours_left": 999999, "daily_left": 999999,
                "daily_used": 0, "credits": credits, "referral_count": ref_count,
                "referrals_cycle": cycle, "referrals_needed": needed,
            }

        now = time.time()
        with self.lock:
            if uid_str in self.approved:
                exp = self.approved[uid_str].get("expires_at", 0)
                if exp > now:
                    diff = exp - now
                    return {
                        "role": "approved", "unlimited": True, "expires_at": exp,
                        "days_left": max(1, math.ceil(diff / 86400)),
                        "hours_left": max(1, math.ceil(diff / 3600)),
                        "daily_left": 999999, "daily_used": 0, "credits": credits,
                        "referral_count": ref_count, "referrals_cycle": cycle, "referrals_needed": needed,
                    }

            today = time.strftime("%Y-%m-%d")
            usage = self.daily_usage.get(uid_str, {})
            count = usage.get("count", 0) if usage.get("date") == today else 0
            daily_left = max(0, 1 - count)
            return {
                "role": "free", "unlimited": False, "expires_at": None,
                "days_left": 0, "hours_left": 0, "daily_used": count,
                "daily_left": daily_left, "credits": credits, "referral_count": ref_count,
                "referrals_cycle": cycle, "referrals_needed": needed,
            }

    def can_bypass(self, user_id: int) -> tuple[bool, str, dict]:
        status = self.get_user_status(user_id)
        if status["role"] in ("owner", "approved"):
            return True, status["role"], status
        if status["daily_left"] > 0:
            return True, "free", status
        if status["credits"] > 0:
            return True, "credits", status
        return False, "limit_reached", status

    def consume_bypass(self, user_id: int, family: str, role: str):
        uid_str = str(user_id)
        today = time.strftime("%Y-%m-%d")
        with self.lock:
            self.all_users.add(user_id)
            if family:
                self.shortener_stats[family] = self.shortener_stats.get(family, 0) + 1

            if role == "free":
                usage = self.daily_usage.get(uid_str, {})
                if usage.get("date") == today:
                    usage["count"] = usage.get("count", 0) + 1
                else:
                    usage = {"date": today, "count": 1}
                self.daily_usage[uid_str] = usage
            elif role == "credits":
                prof = self.user_profiles.get(uid_str, {})
                if prof.get("credits", 0) > 0:
                    prof["credits"] -= 1
                    self.user_profiles[uid_str] = prof
        self.save()

    def get_stats(self) -> dict:
        today = time.strftime("%Y-%m-%d")
        now = time.time()
        with self.lock:
            active_approved = sum(1 for v in self.approved.values() if v.get("expires_at", 0) > now)
            today_active = sum(1 for v in self.daily_usage.values() if v.get("date") == today)
            today_bypasses = sum(v.get("count", 0) for v in self.daily_usage.values() if v.get("date") == today)
            total_keys = len(self.redeem_keys)
            used_keys = sum(1 for k in self.redeem_keys.values() if k.get("used"))
            return {
                "total_users": len(self.all_users),
                "active_approved": active_approved,
                "today_active_users": today_active,
                "today_bypasses": today_bypasses,
                "total_shortener_bypasses": sum(self.shortener_stats.values()),
                "total_keys": total_keys,
                "active_keys": total_keys - used_keys,
            }

    def get_shortener_counts(self) -> dict:
        with self.lock:
            return dict(self.shortener_stats)

    def get_approved_list(self) -> list:
        with self.lock:
            res = []
            now = time.time()
            for uid, data in self.approved.items():
                exp = data.get("expires_at", 0)
                if exp > now:
                    diff = exp - now
                    hours_left = max(1, math.ceil(diff / 3600))
                    days_left = max(1, math.ceil(diff / 86400))
                    res.append({
                        "user_id": uid,
                        "username": data.get("username", "N/A"),
                        "expires_at": exp,
                        "days_left": days_left,
                        "hours_left": hours_left,
                    })
            return res


user_manager = UserManager()


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

def resolve_vipshort_article_url(s, blog_base, myphp_html, notify):
    # Strategy 1: Fast URL slug generation from search query
    m_search = re.search(r'google\.com/search\?q=([^"\'<>\s]+)', myphp_html)
    if m_search:
        raw_q = unquote(m_search.group(1)).replace("+", " ")
        clean_title = re.sub(r'site:[^\s]+', '', raw_q, flags=re.I).strip()
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_title.lower()).strip('-')
        candidate = f"{blog_base.rstrip('/')}/{slug}/"
        notify(f"[vip] derived article URL: {candidate[:65]}")
        return candidate

    # Strategy 2: Blog homepage fallback
    notify(f"[vip] searching blog homepage for active ladder post...")
    r_home = s.get(blog_base, headers={"Referer": "https://www.google.com/"}, timeout=15)
    links = re.findall(r'href="(' + re.escape(blog_base.rstrip("/")) + r'/[a-z0-9-]+/)"', r_home.text)
    skip = ("about-us", "contact-us", "dmca", "privacy-policy", "category", "author", "feed", "wp-")
    valid_posts = [l for l in set(links) if not any(k in l for k in skip)]
    if valid_posts:
        notify(f"[vip] found active post: {valid_posts[0][:65]}")
        return valid_posts[0]

    raise RuntimeError(f"Could not locate active ladder article on blog: {blog_base}")


def bypass_vipshort(s, short_url, notify):
    m_slug = re.search(r"(?:link\.|m\.)?vipshort\.in/([a-zA-Z0-9_-]+)", short_url)
    slug = m_slug.group(1) if m_slug else short_url.rstrip("/").split("/")[-1]
    canonical_short = f"https://link.vipshort.in/{slug}"
    notify(f"[vip] shortlink target: {canonical_short}")

    headers_common = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Step 1: Hop 1 - Get dynamic blog redirect
    notify(f"[vip] querying {canonical_short}...")
    r1 = s.get(canonical_short, headers=headers_common, allow_redirects=False, timeout=15)
    loc1 = r1.headers.get("location") or r1.headers.get("Location")

    if not loc1 and "m.vipshort.in" in r1.url:
        go_page = r1.url
        blog_base = "https://link.vipshort.in/"
        article_url = canonical_short
    elif not loc1:
        raise RuntimeError(f"Expected redirect from {canonical_short}, got status {r1.status_code}")
    else:
        if "href.li/?" in loc1:
            loc1 = loc1.split("href.li/?")[-1]

        parsed_loc = urlparse(loc1)
        blog_base = f"{parsed_loc.scheme}://{parsed_loc.netloc}/"
        notify(f"[vip] dynamic blog host: {blog_base}")

        # Step 2: Hop 2 - Visit myphp.php to register session cookies
        notify(f"[vip] registering session on myphp...")
        r_myphp = s.get(loc1, headers={**headers_common, "Referer": "https://link.vipshort.in/"}, timeout=15)

        # Step 3: Direct article resolution
        article_url = resolve_vipshort_article_url(s, blog_base, r_myphp.text, notify)
        notify(f"[vip] article target: {article_url[:65]}")

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

        m_go = re.search(r'https://(?:m\.|link\.)?vipshort\.in/[^"\'<>\s]+', r_lad.text)
        if m_go:
            go_page = m_go.group(0)
            notify(f"[vip] ladder bypassed instantly! go page: {go_page[:65]}")
        else:
            # Fallback to progressive ladder (vip1: 2 -> 3 -> 4)
            notify("[vip] fast-path unfulfilled, climbing ladder (2 -> 3 -> 4)...")
            current_vip = "2"
            go_page = None
            for _ in range(4):
                time.sleep(1.2)
                r_step = s.post(
                    article_url,
                    data={"vip1": current_vip, "g-recaptcha-response": ""},
                    headers={**headers_common, "Origin": blog_base.rstrip("/"), "Referer": article_url},
                    timeout=15,
                )
                m = re.search(r'https://(?:m\.|link\.)?vipshort\.in/[^"\'<>\s]+', r_step.text)
                if m:
                    go_page = m.group(0)
                    notify(f"[vip] ladder reached go page: {go_page[:65]}")
                    break
                m_next = re.search(r'name="vip1"\s+value="([^"]+)"', r_step.text)
                current_vip = m_next.group(1) if m_next else str(int(current_vip) + 1)

            if not go_page:
                raise RuntimeError("Failed to obtain go-page URL from blog ladder")

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
        raise RuntimeError("Go page layout missing ad_form_data token")

    target_host = "m.vipshort.in"
    s.cookies.set("ab", "2", domain=target_host)

    m_counter = re.search(r'"counter_value":\s*"(\d+)"', r_go.text)
    counter = int(m_counter.group(1)) if m_counter else 5
    wait_time = counter + 0.8
    notify(f"[vip] waiting countdown timer ({wait_time:.1f}s)...")
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

    notify("[vip] submitting final kill request to /links/go...")
    r_kill = s.post(
        f"https://{target_host}/links/go",
        data=payload,
        headers=post_headers,
        timeout=15,
    )

    try:
        res = r_kill.json()
    except Exception:
        raise RuntimeError(f"Non-JSON response from links/go: {r_kill.text[:200]}")

    if res.get("status") == "success" and res.get("url"):
        final_dest = res["url"]
        notify(f"[vip] bypass successful! destination: {final_dest[:65]}...")
        return final_dest
    else:
        raise RuntimeError(f"vipshort rejected links/go: {r_kill.text[:150]}")


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
                notify(f"[aro] ⚠️ Cloudflare Challenge on IP (HTTP {r.status_code})")
                raise RuntimeError("Cloudflare challenge encountered. Link cannot be bypassed at this time.")

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
    raise RuntimeError("walk ran out of hops — destination not found")


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


def bypass_process(link, status_cb=None, **kwargs):
    def notify(msg):
        print(msg, flush=True)
        if status_cb:
            status_cb(msg)

    family, short = normalize(link)
    if family is None:
        raise RuntimeError(f"unrecognized link (supported: vipshort, arolinks, vplink, easysky, monteolympus, shrinkme, dupload): {short[:60]}")

    notify(f"[{family[:3]}] ⚡ Direct high-speed connection")
    s, persona = build_session()
    notify(f"[*] routing: {family} ({persona})")

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
    def __init__(self, bot: telebot.TeleBot, chat_id: int, message_id: int, original_url: str, start_time: float, is_owner: bool = False, role: str = "free"):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.original_url = original_url
        self.start_time = start_time
        self.is_owner = is_owner
        self.role = role
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
        if self.is_owner:
            mode_badge = "👑 <b>Owner Live Terminal:</b>"
            telemetry_block = (
                f"📡 {mode_badge}\n"
                f"<pre>{log_snippet}</pre>\n\n"
            )
        else:
            telemetry_block = (
                f"<blockquote>⚙️ <b>Status:</b> <code>Bypassing multi-gate security & countdowns...</code>\n"
                f"🚀 <b>Routing:</b> <code>Direct High-Speed Pipeline</code></blockquote>\n\n"
            )

        text = (
            f"╭━━━━〔 ⚡ <b>BYPASSING IN PROGRESS...</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Target Link:</b>\n"
            f"<code>{self.original_url}</code></blockquote>\n\n"
            f"{telemetry_block}"
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
        role_label = "👑 Owner" if self.is_owner else ("💎 Premium VIP" if self.role == "approved" else "🆓 Free Tier")
        footer_tip = ""
        if self.role == "free":
            footer_tip = f"\n💡 <i>Free Tier: You used your 1 daily bypass. Contact {DEVELOPER} for unlimited access!</i>"

        text = (
            f"╭━━━━〔 ⚡ <b>BYPASS SUCCESSFUL</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Original URL:</b>\n"
            f"<code>{self.original_url}</code></blockquote>\n\n"
            f"<blockquote>🎯 <b>Final Destination:</b>\n"
            f"<code>{final_url}</code></blockquote>\n\n"
            f"╭─ 📊 <b>Execution Details</b>\n"
            f"├ ⏱ <b>Time Taken :</b> <code>{elapsed:.2f}s</code>\n"
            f"├ 🛡 <b>Engine     :</b> <code>TLS Impersonation v2</code>\n"
            f"├ 👤 <b>Access Tier:</b> <code>{role_label}</code>\n"
            f"╰ 👨‍💻 <b>Developer  :</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯{footer_tip}"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        if final_url.startswith("http"):
            buttons.append(types.InlineKeyboardButton("🚀 Open Final Link", url=final_url))
        dev_handle = DEVELOPER.lstrip("@")
        buttons.append(types.InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{dev_handle}"))
        if self.role == "free":
            buttons.append(types.InlineKeyboardButton(f"💎 Upgrade to VIP (DM {DEVELOPER})", url=f"https://t.me/{dev_handle}"))
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
            f"💡 <i>Tip: The link may be dead, expired, or temporarily unreachable.</i>"
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

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()

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

    # Fetch bot username dynamically and verify token
    bot_username = "Bot"
    try:
        me = bot.get_me()
        bot_username = me.username or "Bot"
        print(f"[*] Telegram Auth SUCCESS: @{bot_username} (Bot ID: {me.id}, Name: {me.first_name})", flush=True)
    except Exception as e:
        print(f"[!] CRITICAL: Telegram bot authentication failed for token! Check BOT_TOKEN: {e}", flush=True)

    # Verify channel accessibility at startup
    try:
        chat_info = bot.get_chat(FORCE_CHANNEL_ID)
        print(f"[*] Force-Join Channel verified: {chat_info.title} (ID: {FORCE_CHANNEL_ID})", flush=True)
    except Exception as e:
        print(f"[!] ATTENTION: Cannot access Force-Join Channel ({FORCE_CHANNEL_ID}): {e}", flush=True)
        print(f"    ACTION REQUIRED: Add the bot as an ADMINISTRATOR in channel {FORCE_CHANNEL_ID}!", flush=True)

    # Verify log channel accessibility at startup
    try:
        log_info = bot.get_chat(LOG_CHANNEL_ID)
        print(f"[*] Silent Log Channel verified: {log_info.title} (ID: {LOG_CHANNEL_ID})", flush=True)
    except Exception as e:
        print(f"[!] ATTENTION: Cannot access Silent Log Channel ({LOG_CHANNEL_ID}): {e}", flush=True)
        print(f"    ACTION REQUIRED: Add the bot as an ADMINISTRATOR in channel {LOG_CHANNEL_ID}!", flush=True)

    # Bulletproof safe send/reply wrappers
    _orig_send_message = bot.send_message
    _orig_reply_to = bot.reply_to
    _orig_edit_message_text = bot.edit_message_text

    def safe_send_message(chat_id, text, reply_markup=None, reply_to_message_id=None, parse_mode="HTML", **kwargs):
        try:
            return _orig_send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
                **kwargs
            )
        except Exception as e:
            err = str(e).lower()
            print(f"[!] Telegram API send error to chat {chat_id}: {e}", flush=True)
            if ("replied" in err or "reply" in err) and reply_to_message_id:
                try:
                    return _orig_send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        **kwargs
                    )
                except Exception as e2:
                    print(f"[!] Retry without reply failed: {e2}", flush=True)
            if "entities" in err or "parse" in err or "tag" in err:
                plain_text = re.sub(r"<[^>]+>", "", str(text))
                try:
                    return _orig_send_message(
                        chat_id=chat_id,
                        text=plain_text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        **kwargs
                    )
                except Exception as e3:
                    print(f"[!] Fallback plain text send failed: {e3}", flush=True)
            return None

    def safe_reply_to(msg, text, reply_markup=None, parse_mode="HTML", **kwargs):
        chat_id = msg.chat.id if hasattr(msg, "chat") else msg
        msg_id = msg.message_id if hasattr(msg, "message_id") else None
        return safe_send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            reply_to_message_id=msg_id,
            parse_mode=parse_mode,
            **kwargs
        )

    def safe_edit_message_text(text, chat_id=None, message_id=None, parse_mode="HTML", **kwargs):
        try:
            return _orig_edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode=parse_mode, **kwargs)
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return None
            if "entities" in err or "parse" in err or "tag" in err:
                plain_text = re.sub(r"<[^>]+>", "", str(text))
                try:
                    return _orig_edit_message_text(plain_text, chat_id=chat_id, message_id=message_id, parse_mode=None, **kwargs)
                except Exception:
                    pass
            return None

    bot.send_message = safe_send_message
    bot.reply_to = safe_reply_to
    bot.edit_message_text = safe_edit_message_text

    # Global live incoming message logging middleware
    try:
        @bot.middleware_handler(update_types=['message', 'edited_message'])
        def log_incoming_message(bot_instance, message):
            uid = message.from_user.id if message.from_user else message.chat.id
            uname = message.from_user.username if message.from_user else "N/A"
            raw_text = message.text or message.caption or "<media/empty>"
            print(f"[*] [INCOMING MSG] User: {uid} (@{uname}) | Chat: {message.chat.id} | Content: {raw_text[:80]!r}", flush=True)

        @bot.middleware_handler(update_types=['callback_query'])
        def log_incoming_callback(bot_instance, call):
            uid = call.from_user.id if call.from_user else "unknown"
            uname = call.from_user.username if call.from_user else "N/A"
            print(f"[*] [INCOMING CALLBACK] User: {uid} (@{uname}) | Data: {call.data!r}", flush=True)
    except Exception as e:
        print(f"[!] Middleware note: {e}", flush=True)

    def check_user_channel_member(user_id: int) -> bool:
        if user_manager.is_owner(user_id):
            return True
        try:
            m = bot.get_chat_member(FORCE_CHANNEL_ID, user_id)
            return m.status in ("creator", "administrator", "member", "restricted")
        except Exception as e:
            err = str(e).lower()
            if "chat not found" in err or "bot was kicked" in err or "not a member" in err or "admin" in err:
                print(f"[!] Deployment Channel Check Warning: Bot is NOT an administrator in channel {FORCE_CHANNEL_ID}! Add bot to channel as admin. Error: {e}", flush=True)
            return False

    def get_force_join_card():
        card = (
            f"╭━━━━〔 🔒 <b>CHANNEL JOIN REQUIRED</b> 〕━━━━╮\n\n"
            f"<blockquote>⚠️ <b>Access Restricted!</b>\n"
            f"You must join our official channel to use this bot,\n"
            f"bypass links, earn free credits, and claim rewards!</blockquote>\n\n"
            f"╭─ 📢 <b>Official Channel</b>\n"
            f"╰ 👉 <a href=\"{FORCE_CHANNEL_LINK}\"><b>Click Here to Join Channel</b></a>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
            f"👉 <i>Step 1: Click 'Join Channel' below & join.\n"
            f"👉 Step 2: Click 'Verify Membership' to continue!</i>"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Join Channel", url=FORCE_CHANNEL_LINK),
            types.InlineKeyboardButton("🔄 Verify Membership", callback_data="cb_verify_join")
        )
        return card, markup

    # ========================================================
    # USER COMMANDS
    # ========================================================

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        uname = msg.from_user.username if msg.from_user else None

        # Check for deep-link referral
        parts = (msg.text or "").strip().split()
        pending_ref = None
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                cand_ref = int(parts[1].replace("ref_", "").strip())
                if cand_ref != uid:
                    pending_ref = cand_ref
            except ValueError:
                pass

        user_manager.register(uid, uname, pending_ref=pending_ref)

        # Force Join check (Owner is automatically exempt)
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        # If user joined channel, process referral confirmation if any
        is_ref, ref_id, unlocked = user_manager.confirm_channel_joined(uid)
        if is_ref and ref_id:
            try:
                ref_uname = f"@{uname}" if uname else f"User <code>{uid}</code>"
                r_stat = user_manager.get_user_status(ref_id)
                if unlocked:
                    reward_notice = (
                        f"\n\n🎉 <b>CONGRATULATIONS! 5/5 REFERRALS REACHED!</b>\n"
                        f"⚡ You have unlocked <b>6 HOURS OF UNLIMITED BYPASSES</b>!\n"
                        f"🚀 <i>Enjoy zero countdowns and unlimited links!</i>"
                    )
                else:
                    bar = make_progress_bar(r_stat['referrals_cycle'], 5)
                    reward_notice = (
                        f"\n\n📊 <b>Milestone Progress:</b> <code>{bar} {r_stat['referrals_cycle']}/5</code>\n"
                        f"💡 <i>{r_stat['referrals_needed']} more referral(s) needed to unlock 6h unlimited!</i>"
                    )
                bot.send_message(
                    ref_id,
                    f"╭━━━━〔 👥 <b>NEW REFERRAL CONFIRMED!</b> 〕━━━━╮\n\n"
                    f"<blockquote>👤 <b>Member Joined:</b> {ref_uname}\n"
                    f"✅ <i>Status: Verified channel member!</i></blockquote>"
                    f"{reward_notice}\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        status = user_manager.get_user_status(uid)
        is_owner = user_manager.is_owner(uid)

        if is_owner:
            badge = "👑 <b>Owner & Developer</b> (Full Root Control)"
        elif status["role"] == "approved":
            time_text = f"{status['days_left']}d" if status['days_left'] > 2 else f"{status['hours_left']}h"
            badge = f"💎 <b>VIP Approved Member</b> (Unlimited — {time_text} left)"
        else:
            badge = f"🆓 <b>Free Tier Member</b> (1 daily free — {status['daily_left']}/1 left | Credits: <b>{status['credits']}</b>)"

        welcome = (
            f"╭━━━━〔 ⚡ <b>MASTER BYPASS BOT</b> 〕━━━━╮\n\n"
            f"🚀 <i>Instant Link Shortener Bypasser</i>\n"
            f"Skips countdown timers, gateway loops, and ads!\n\n"
            f"╭─ 👤 <b>Your Membership</b>\n"
            f"╰ {badge}\n\n"
            f"╭─ 💎 <b>Supported Networks</b>\n"
            f"├ 🌐 <code>arolinks.com</code> (direct multi-lap)\n"
            f"├ 🔗 <code>vipshort.in</code> (direct fast-hop)\n"
            f"├ ⚡ <code>vplink.in / vplinks.in</code> (direct)\n"
            f"├ 🌌 <code>easysky.in / m.easysky.in</code> (direct SafeLink)\n"
            f"├ 🏛️ <code>monteolympus.com</code> (instant 8-gate skip)\n"
            f"├ 🎯 <code>shrinkme.click / io</code> (mrproblogger bypass)\n"
            f"╰ 📦 <code>dupload.net / xyz</code> (direct CDN)\n\n"
            f"╭─ 📖 <b>Quick Navigation</b>\n"
            f"├ 🔗 Send any supported link directly to this chat\n"
            f"├ 📋 Type <code>/cmds</code> to view all user commands\n"
            f"╰ 👥 Type <code>/refer</code> to earn free unlimited hours!\n\n"
            f"╭─ 👨‍💻 <b>Developer</b>\n"
            f"╰ <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        dev_handle = DEVELOPER.lstrip("@")
        buttons = [
            types.InlineKeyboardButton("📋 All Commands", callback_data="cb_cmds"),
            types.InlineKeyboardButton("👥 Referral Program", callback_data="cb_refer"),
            types.InlineKeyboardButton("💳 My Plan", callback_data="cb_myplan"),
            types.InlineKeyboardButton("👨‍💻 Developer Profile", url=f"https://t.me/{dev_handle}"),
        ]
        markup.add(*buttons)
        bot.reply_to(msg, welcome, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["cmds"])
    def cmd_cmds(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        text = (
            f"╭━━━━〔 📋 <b>USER COMMANDS CONSOLE</b> 〕━━━━╮\n\n"
            f"╭─ 🚀 <b>Link Bypassing</b>\n"
            f"├ 🔗 <b>Send any link directly to this chat</b>\n"
            f"╰ ⚡ Automatically skipped in seconds without ads!\n\n"
            f"╭─ 👤 <b>Account & Rewards</b>\n"
            f"├ 💳 <code>/myplan</code> - Check account tier, quota & credits\n"
            f"├ 👥 <code>/refer</code> - Invite friends (5 refers = 6h unlimited!)\n"
            f"├ 🎁 <code>/redeem &lt;code&gt;</code> - Redeem VIP time or credit keys\n"
            f"├ 💰 <code>/credits</code> - Check your bypass credits balance\n"
            f"╰ 📋 <code>/cmds</code> - View this user commands list\n\n"
            f"╭─ 💎 <b>Supported Shorteners</b>\n"
            f"├ <code>arolinks.com</code>, <code>vipshort.in</code>, <code>vplink.in</code>\n"
            f"├ <code>easysky.in</code>, <code>monteolympus.com</code>\n"
            f"╰ <code>shrinkme.click</code>, <code>dupload.net</code>\n\n"
            f"╭─ 👨‍💻 <b>Developer</b>\n"
            f"╰ <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💳 My Plan", callback_data="cb_myplan"),
            types.InlineKeyboardButton("👥 Referral Link", callback_data="cb_refer")
        )
        bot.reply_to(msg, text, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["myplan", "plan", "profile"])
    def cmd_myplan(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        status = user_manager.get_user_status(uid)
        is_owner = user_manager.is_owner(uid)
        dev_handle = DEVELOPER.lstrip("@")
        markup = types.InlineKeyboardMarkup(row_width=1)

        if is_owner:
            card = (
                f"╭━━━━〔 👑 <b>OWNER PROFILE</b> 〕━━━━╮\n\n"
                f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                f"🎖️ <b>Tier:</b> <code>System Owner & Developer</code>\n"
                f"⚡ <b>Bypasses:</b> <code>Unlimited ∞</code>\n"
                f"📡 <b>Telemetry:</b> <code>Full Raw Terminal Stream</code>\n"
                f"🛡️ <b>Privileges:</b> <code>Complete Root Administration</code></blockquote>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup.add(types.InlineKeyboardButton("👑 Owner Console", callback_data="cb_stat"))
        elif status["role"] == "approved":
            exp_date = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(status['expires_at']))
            time_left_str = f"{status['days_left']} days" if status['days_left'] > 2 else f"{status['hours_left']} hours"
            card = (
                f"╭━━━━〔 💎 <b>VIP MEMBER PROFILE</b> 〕━━━━╮\n\n"
                f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                f"🎖️ <b>Tier:</b> <code>Approved VIP Subscriber</code>\n"
                f"⚡ <b>Bypasses:</b> <code>Unlimited Daily Access</code>\n"
                f"⏳ <b>Time Left:</b> <code>{time_left_str}</code>\n"
                f"📅 <b>Expires At:</b> <code>{exp_date}</code>\n"
                f"💰 <b>Credits Reserve:</b> <code>{status['credits']} credits</code></blockquote>\n\n"
                f"🚀 <i>Enjoy zero countdowns and priority high-speed bypassing!</i>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup.add(types.InlineKeyboardButton("👨‍💻 Contact Support", url=f"https://t.me/{dev_handle}"))
        else:
            used = status.get("daily_used", 0)
            left = status.get("daily_left", 1)
            bar = "🟩" if left > 0 else "🟥"
            ref_bar = make_progress_bar(status['referrals_cycle'], 5)
            card = (
                f"╭━━━━〔 🆓 <b>FREE TIER PROFILE</b> 〕━━━━╮\n\n"
                f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                f"🎖️ <b>Tier:</b> <code>Free Member</code>\n"
                f"🎯 <b>Daily Free Quota:</b> <code>1 bypass / day</code>\n"
                f"📊 <b>Quota Status:</b> <code>{bar} {used}/1 Used ({left} Left)</code>\n"
                f"💰 <b>Credits Balance:</b> <code>{status['credits']} credits</code>\n"
                f"👥 <b>Referral Progress:</b> <code>{ref_bar} {status['referrals_cycle']}/5</code></blockquote>\n\n"
                f"╭─ ⚡ <b>Unlock Unlimited VIP</b>\n"
                f"├ 🚀 Invite 5 friends via <code>/refer</code> (get 6h unlimited!)\n"
                f"├ 🎁 Redeem gift keys via <code>/redeem</code>\n"
                f"╰ 💬 <b>DM {DEVELOPER} for permanent VIP access!</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup.add(
                types.InlineKeyboardButton("👥 Referral Program", callback_data="cb_refer"),
                types.InlineKeyboardButton(f"💬 DM {DEVELOPER} for VIP", url=f"https://t.me/{dev_handle}")
            )

        bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["refer", "referral"])
    def cmd_refer(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        status = user_manager.get_user_status(uid)
        ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
        cycle = status["referrals_cycle"]
        needed = status["referrals_needed"]
        bar = make_progress_bar(cycle, 5)

        card = (
            f"╭━━━━〔 👥 <b>REFERRAL REWARDS PROGRAM</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Your Exclusive Referral Link:</b>\n"
            f"<code>{ref_link}</code></blockquote>\n\n"
            f"╭─ 🎁 <b>How it Works</b>\n"
            f"├ 1. Share your link with friends or groups\n"
            f"├ 2. Friend starts the bot and joins our channel\n"
            f"╰ 3. <b>Every 5 referrals unlock 6 HOURS UNLIMITED VIP!</b>\n\n"
            f"╭─ 📊 <b>Your Referral Metrics</b>\n"
            f"├ 👥 <b>Total Referred  :</b> <code>{status['referral_count']} users</code>\n"
            f"├ 🎯 <b>Current Cycle   :</b> <code>{bar} {cycle}/5</code>\n"
            f"╰ ⏳ <b>Needed for Reward:</b> <code>{needed} more referral(s)</code>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
            f"🚀 <i>Share your link to unlock unlimited instant bypasses for free!</i>"
        )
        share_url = f"https://t.me/share/url?url={ref_link}&text=Bypass%20all%20link%20shorteners%20instantly%20with%20zero%20ads%20and%20countdowns!"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 Share Referral Link", url=share_url),
            types.InlineKeyboardButton("💳 Check My Plan", callback_data="cb_myplan"),
        )
        bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["credits"])
    def cmd_credits(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        credits, expiring = user_manager.get_credit_summary(uid)
        now = time.time()
        expiry_lines = []
        for b in expiring:
            rem_sec = max(0, int(b["expires_at"] - now))
            if rem_sec > 86400:
                rem_str = f"{rem_sec // 86400}d {(rem_sec % 86400) // 3600}h"
            elif rem_sec > 3600:
                rem_str = f"{rem_sec // 3600}h {(rem_sec % 3600) // 60}m"
            else:
                rem_str = f"{max(1, rem_sec // 60)}m"
            exp_date = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(b["expires_at"]))
            expiry_lines.append(f"│  ⏳ <code>{b['amount']} credits</code> expire in <b>{rem_str}</b> (<code>{exp_date}</code>)")

        expiry_block = ""
        if expiry_lines:
            expiry_block = f"╭─ ⏳ <b>Expiring Credits Notice</b>\n" + "\n".join(expiry_lines) + "\n╰────────────────────────────\n\n"

        card = (
            f"╭━━━━〔 💰 <b>BYPASS CREDITS BALANCE</b> 〕━━━━╮\n\n"
            f"<blockquote>👤 <b>User ID:</b> <code>{uid}</code>\n"
            f"💎 <b>Current Balance:</b> <code>{credits} credits</code></blockquote>\n\n"
            f"{expiry_block}"
            f"╭─ 💡 <b>How Credits Work</b>\n"
            f"├ 🎯 <b>1 Credit = 1 Extra Link Bypass</b>\n"
            f"├ ⚡ Used automatically when your daily free bypass is spent\n"
            f"├ 🛡 Expiring credits are always spent first before permanent credits\n"
            f"╰ 🎁 Redeem voucher keys via <code>/redeem</code> or reply to key!\n\n"
            f"╭─ ➕ <b>How to Get Credits</b>\n"
            f"├ 🎁 Redeem voucher keys via <code>/redeem &lt;code&gt;</code>\n"
            f"╰ 💬 Contact <b>{DEVELOPER}</b> to purchase or claim credits\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        dev_handle = DEVELOPER.lstrip("@")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"💬 Get Credits from {DEVELOPER}", url=f"https://t.me/{dev_handle}"))
        bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["redeem"])
    def cmd_redeem(msg):
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not check_user_channel_member(uid):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        parts = (msg.text or "").strip().split()
        target_code = None

        if len(parts) >= 2 and parts[1].strip():
            target_code = parts[1].strip().upper()
        elif msg.reply_to_message:
            replied_text = (msg.reply_to_message.text or msg.reply_to_message.caption or "").strip()
            available = user_manager.find_available_keys_in_text(uid, replied_text)
            if available:
                target_code = available[0]
            else:
                # Check if there are keys in text that are already redeemed or expired
                all_found = re.findall(r"VIP-(?:TIME|CRED)-[A-Za-z0-9\-]+", replied_text, re.I)
                if all_found:
                    bot.reply_to(
                        msg,
                        "❌ <b>No Redeemable Keys Available!</b>\n"
                        "All keys in the replied message have already been claimed by you, reached their user limit, or expired.",
                        parse_mode="HTML"
                    )
                    return
                else:
                    bot.reply_to(
                        msg,
                        "⚠️ <b>No Keys Detected!</b>\n"
                        "The message you replied to does not contain any valid <code>VIP-...</code> redeem keys.",
                        parse_mode="HTML"
                    )
                    return

        if not target_code:
            bot.reply_to(
                msg,
                "⚠️ <b>How to Redeem:</b>\n\n"
                "1. <b>Direct:</b> <code>/redeem VIP-TIME-7D-ABC123</code>\n"
                "2. <b>Reply:</b> Reply <code>/redeem</code> to any message containing keys!\n"
                "3. <b>Direct Key:</b> Send any <code>VIP-...</code> key directly to this chat!",
                parse_mode="HTML"
            )
            return

        ok, res_text, entry = user_manager.redeem_key(uid, target_code)
        if ok:
            card = (
                f"╭━━━━〔 🎁 <b>REDEEM SUCCESSFUL</b> 〕━━━━╮\n\n"
                f"<blockquote>🔑 <b>Redeemed Key:</b> <code>{target_code}</code></blockquote>\n\n"
                f"{res_text}\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Check My Plan", callback_data="cb_myplan"))
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
        else:
            bot.reply_to(msg, res_text, parse_mode="HTML")

    # ========================================================
    # OWNER ADMIN COMMANDS (STRICT SILENT REJECTION FOR NON-OWNERS)
    # ========================================================

    def check_owner_or_silent_reject(msg) -> bool:
        uid = msg.from_user.id if msg.from_user else msg.chat.id
        if not user_manager.is_owner(uid):
            cmd_name = (msg.text or "").split()[0] if msg.text else "command"
            print(f"[*] [SILENT IGNORE] Non-owner UID={uid} attempted owner command: {cmd_name} (Configured OWNER_ID={OWNER_ID})", flush=True)
            return False
        return True

    @bot.message_handler(commands=["ocmds", "ownerhelp"])
    def cmd_ocmds(msg):
        if not check_owner_or_silent_reject(msg):
            return  # SILENT REJECTION - NEVER EXPOSE OWNER CMDS

        text = (
            f"╭━━━━〔 👑 <b>OWNER ROOT CONSOLE</b> 〕━━━━╮\n\n"
            f"╭─ 👥 <b>User VIP Management</b>\n"
            f"├ ➕ <code>/add &lt;userid&gt; &lt;days&gt;</code> - Grant VIP days\n"
            f"├ ⏳ <code>/addtime &lt;userid&gt; &lt;hours&gt;</code> - Grant VIP hours\n"
            f"├ ➖ <code>/rm &lt;userid&gt;</code> - Revoke user VIP access\n"
            f"├ 💰 <code>/addcredit &lt;userid&gt; &lt;amount&gt;</code> - Add credits to user\n"
            f"╰ 🔻 <code>/deduct &lt;userid&gt; &lt;amount&gt;</code> - Deduct credits from user\n\n"
            f"╭─ 🔑 <b>Key Generation Engine</b>\n"
            f"├ 🎟 <code>/genkey &lt;type&gt; &lt;val&gt; [flags]</code>\n"
            f"│  └ e.g. <code>/genkey credit 10 users:10 cexp:1h kexp:24h</code>\n"
            f"├ 📦 <code>/genkeys &lt;count&gt; &lt;type&gt; &lt;val&gt; [flags]</code> - Bulk key generation\n"
            f"╰ 🎟 <code>/keys</code> - View active available keys & claims\n\n"
            f"╭─ 📢 <b>Broadcast Engine</b>\n"
            f"├ 📢 <code>/broadcast &lt;text&gt;</code> - Broadcast text to all users\n"
            f"╰ 📎 <b>Reply</b> <code>/broadcast</code> to any media message to copy-broadcast!\n\n"
            f"╭─ 📊 <b>Telemetry & Analytics</b>\n"
            f"├ 📊 <code>/stat</code> - Real-time system ecosystem metrics\n"
            f"├ 📈 <code>/show</code> - Bypass counts per shortener\n"
            f"╰ 👥 <code>/users</code> - List active VIP subscribers\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, text, parse_mode="HTML")

    @bot.message_handler(commands=["add"])
    def cmd_add(msg):
        if not check_owner_or_silent_reject(msg):
            return

        parts = (msg.text or "").strip().split()
        if len(parts) < 3:
            bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/add &lt;userid&gt; &lt;days&gt;</code>", parse_mode="HTML")
            return

        try:
            target_uid = int(parts[1].strip())
            days = int(parts[2].strip())
            if days <= 0:
                raise ValueError()
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID or days.", parse_mode="HTML")
            return

        new_exp = user_manager.add_approved(target_uid, days)
        exp_date_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(new_exp))
        days_left = max(1, math.ceil((new_exp - time.time()) / 86400))

        card = (
            f"╭━━━━〔 ✅ <b>VIP ACCESS GRANTED</b> 〕━━━━╮\n\n"
            f"<blockquote>👤 <b>Target User:</b> <code>{target_uid}</code>\n"
            f"➕ <b>Added Duration:</b> <code>+{days} days</code>\n"
            f"⏳ <b>Total Remaining:</b> <code>{days_left} days</code>\n"
            f"📅 <b>Expires At:</b> <code>{exp_date_str}</code>\n"
            f"⚡ <b>Privilege:</b> <code>Unlimited Daily Bypasses</code></blockquote>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

        try:
            user_notify = (
                f"╭━━━━〔 🎉 <b>VIP ACCESS ACTIVATED!</b> 〕━━━━╮\n\n"
                f"<blockquote>💎 Your account has been upgraded to <b>VIP Approved</b>!\n"
                f"➕ <b>Duration:</b> <code>{days} days</code>\n"
                f"📅 <b>Valid Until:</b> <code>{exp_date_str}</code>\n"
                f"⚡ <b>Privilege:</b> <code>Unlimited Daily Link Bypasses</code></blockquote>\n\n"
                f"🚀 <i>Enjoy blazing-fast ad-free link bypassing!</i>\n"
                f"👨‍💻 <i>Approved by {DEVELOPER}</i>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            bot.send_message(target_uid, user_notify, parse_mode="HTML")
        except Exception:
            pass

    @bot.message_handler(commands=["addtime"])
    def cmd_addtime(msg):
        if not check_owner_or_silent_reject(msg):
            return

        parts = (msg.text or "").strip().split()
        if len(parts) < 3:
            bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/addtime &lt;userid&gt; &lt;hours&gt;</code>", parse_mode="HTML")
            return

        try:
            target_uid = int(parts[1].strip())
            hours = int(parts[2].strip())
            if hours <= 0:
                raise ValueError()
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID or hours.", parse_mode="HTML")
            return

        new_exp = user_manager.add_time(target_uid, seconds=hours * 3600)
        exp_date_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(new_exp))
        hours_left = max(1, math.ceil((new_exp - time.time()) / 3600))

        card = (
            f"╭━━━━〔 ✅ <b>VIP TIME GRANTED</b> 〕━━━━╮\n\n"
            f"<blockquote>👤 <b>Target User:</b> <code>{target_uid}</code>\n"
            f"➕ <b>Added Duration:</b> <code>+{hours} hours</code>\n"
            f"⏳ <b>Total Remaining:</b> <code>{hours_left} hours</code>\n"
            f"📅 <b>Expires At:</b> <code>{exp_date_str}</code>\n"
            f"⚡ <b>Privilege:</b> <code>Unlimited Daily Bypasses</code></blockquote>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

        try:
            bot.send_message(
                target_uid,
                f"🎉 <b>VIP Access Activated!</b>\nYou have been granted <b>{hours} hours</b> of Unlimited Bypasses!\nValid until: <code>{exp_date_str}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    @bot.message_handler(commands=["rm", "remove"])
    def cmd_rm(msg):
        if not check_owner_or_silent_reject(msg):
            return

        parts = (msg.text or "").strip().split()
        if len(parts) < 2:
            bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/rm &lt;userid&gt;</code>", parse_mode="HTML")
            return

        try:
            target_uid = int(parts[1].strip())
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID.", parse_mode="HTML")
            return

        removed = user_manager.remove_approved(target_uid)
        if removed:
            card = (
                f"╭━━━━〔 🗑️ <b>VIP ACCESS REVOKED</b> 〕━━━━╮\n\n"
                f"<blockquote>👤 <b>Target User:</b> <code>{target_uid}</code>\n"
                f"🔻 <b>New Tier:</b> <code>Free Tier (1 bypass/day)</code></blockquote>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            bot.reply_to(msg, card, parse_mode="HTML")
            try:
                bot.send_message(
                    target_uid,
                    f"⚠️ <b>VIP Access Update:</b> Your VIP access has been revoked or expired.\n"
                    f"You have been returned to the Free Tier (1 bypass/day).\nContact {DEVELOPER} to renew.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        else:
            bot.reply_to(msg, f"⚠️ User <code>{target_uid}</code> was not in VIP list.", parse_mode="HTML")

    @bot.message_handler(commands=["addcredit"])
    def cmd_addcredit(msg):
        if not check_owner_or_silent_reject(msg):
            return

        parts = (msg.text or "").strip().split()
        if len(parts) < 3:
            bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/addcredit &lt;userid&gt; &lt;amount&gt;</code>", parse_mode="HTML")
            return

        try:
            target_uid = int(parts[1].strip())
            amount = int(parts[2].strip())
            if amount <= 0:
                raise ValueError()
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID or credit amount.", parse_mode="HTML")
            return

        new_bal = user_manager.add_credits(target_uid, amount)
        card = (
            f"╭━━━━〔 💰 <b>CREDITS ADDED</b> 〕━━━━╮\n\n"
            f"<blockquote>👤 <b>User ID:</b> <code>{target_uid}</code>\n"
            f"➕ <b>Added:</b> <code>+{amount} credits</code>\n"
            f"💎 <b>New Balance:</b> <code>{new_bal} credits</code></blockquote>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

        try:
            bot.send_message(
                target_uid,
                f"🎉 <b>Credits Received!</b>\nOwner added <b>+{amount} Credits</b> to your account!\n💰 New Balance: <b>{new_bal} Credits</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    @bot.message_handler(commands=["deduct"])
    def cmd_deduct(msg):
        if not check_owner_or_silent_reject(msg):
            return

        parts = (msg.text or "").strip().split()
        if len(parts) < 3:
            bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/deduct &lt;userid&gt; &lt;amount&gt;</code>", parse_mode="HTML")
            return

        try:
            target_uid = int(parts[1].strip())
            amount = int(parts[2].strip())
            if amount <= 0:
                raise ValueError()
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID or credit amount.", parse_mode="HTML")
            return

        new_bal = user_manager.deduct_credits(target_uid, amount)
        card = (
            f"╭━━━━〔 🔻 <b>CREDITS DEDUCTED</b> 〕━━━━╮\n\n"
            f"<blockquote>👤 <b>User ID:</b> <code>{target_uid}</code>\n"
            f"➖ <b>Deducted:</b> <code>-{amount} credits</code>\n"
            f"💎 <b>New Balance:</b> <code>{new_bal} credits</code></blockquote>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

    @bot.message_handler(commands=["genkey", "genkeys"])
    def cmd_genkey(msg):
        if not check_owner_or_silent_reject(msg):
            return

        raw = (msg.text or "").strip()
        parts = raw.split()
        is_genkeys = parts[0].lower().startswith("/genkeys")

        count = 1
        pos_args = []
        options = {}

        idx = 1
        if is_genkeys and len(parts) > 1:
            try:
                count = int(parts[1])
                idx = 2
            except ValueError:
                count = 1

        for token in parts[idx:]:
            if ":" in token:
                k, v = token.split(":", 1)
                options[k.lower().strip()] = v.strip()
            else:
                pos_args.append(token)

        if "count" in options:
            try:
                count = int(options["count"])
            except ValueError:
                count = 1

        if len(pos_args) < 2:
            help_text = (
                f"╭━━━━〔 🎟 <b>KEY GENERATION GUIDE</b> 〕━━━━╮\n\n"
                f"<blockquote><b>Basic Usage:</b>\n"
                f"<code>/genkey time 6h</code> (or <code>12h</code>, <code>1d</code>, <code>30d</code>)\n"
                f"<code>/genkey credit 20</code></blockquote>\n\n"
                f"╭─ ⚡ <b>Advanced Parameters</b>\n"
                f"├ 👥 <code>users:N</code> - Usable by N persons (e.g. <code>users:10</code>)\n"
                f"├ ⏳ <code>kexp:TIME</code> - Key expires in TIME (e.g. <code>kexp:24h</code>, <code>kexp:7d</code>)\n"
                f"├ ⌛ <code>cexp:TIME</code> - Credits expire in TIME (e.g. <code>cexp:1h</code>, <code>cexp:10m</code>)\n"
                f"╰ 📦 <code>count:N</code> - Generate N keys at once (or use <code>/genkeys N ...</code>)\n\n"
                f"╭─ 💡 <b>Real Examples</b>\n"
                f"├ <code>/genkey credit 10 users:10 cexp:1h kexp:24h</code>\n"
                f"├ <code>/genkey time 1d users:5 kexp:48h</code>\n"
                f"╰ <code>/genkeys 20 credit 5 cexp:2h</code>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            bot.reply_to(msg, help_text, parse_mode="HTML")
            return

        k_type = pos_args[0].lower().strip()
        k_val = pos_args[1].strip()

        max_uses = 1
        if "users" in options:
            try: max_uses = int(options["users"])
            except ValueError: pass
        elif "uses" in options:
            try: max_uses = int(options["uses"])
            except ValueError: pass

        kexp_secs = None
        if "kexp" in options:
            try: kexp_secs = parse_duration_string(options["kexp"])
            except Exception: pass

        cexp_secs = None
        if "cexp" in options:
            try: cexp_secs = parse_duration_string(options["cexp"])
            except Exception: pass

        try:
            if count > 1:
                batch = user_manager.create_batch_keys(
                    count=min(count, 100),
                    key_type=k_type,
                    val_str=k_val,
                    max_uses=max_uses,
                    key_expiry_secs=kexp_secs,
                    credit_duration_secs=cexp_secs
                )
                if not batch:
                    bot.reply_to(msg, "❌ Failed to generate keys.", parse_mode="HTML")
                    return

                lines = []
                for i, (cd, _) in enumerate(batch, 1):
                    lines.append(f"<code>{cd}</code>")

                kexp_str = f"{options.get('kexp', '')}" if kexp_secs else "Permanent"
                cexp_str = f"{options.get('cexp', '')}" if cexp_secs else "No Expiry"
                codes_block = "\n".join(lines)

                card = (
                    f"╭━━━━〔 🎟 <b>BATCH KEYS GENERATED ({len(batch)})</b> 〕━━━━╮\n\n"
                    f"<blockquote>🏷 <b>Type:</b> <code>{k_type.upper()}</code>\n"
                    f"👥 <b>Max Users / Key:</b> <code>{max_uses}</code>\n"
                    f"⏳ <b>Key Expiry:</b> <code>{kexp_str}</code>\n"
                    f"⌛ <b>Credit Duration:</b> <code>{cexp_str}</code></blockquote>\n\n"
                    f"╭─ 🔑 <b>Keys List (Click to copy)</b>\n"
                    f"{codes_block}\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                bot.reply_to(msg, card, parse_mode="HTML")
            else:
                ok, code, desc = user_manager.create_key(
                    key_type=k_type,
                    val_str=k_val,
                    max_uses=max_uses,
                    key_expiry_secs=kexp_secs,
                    credit_duration_secs=cexp_secs
                )
                if ok:
                    kexp_str = f"{options.get('kexp', '')}" if kexp_secs else "Never Expires"
                    cexp_str = f"{options.get('cexp', '')}" if cexp_secs else "Permanent"
                    card = (
                        f"╭━━━━〔 🎟 <b>KEY GENERATED</b> 〕━━━━╮\n\n"
                        f"<blockquote>🔑 <b>Redeem Key:</b>\n<code>{code}</code></blockquote>\n\n"
                        f"╭─ 📦 <b>Key Properties</b>\n"
                        f"├ 🏷 <b>Type           :</b> <code>{k_type.upper()}</code>\n"
                        f"├ 🎁 <b>Reward         :</b> <code>{desc}</code>\n"
                        f"├ 👥 <b>Allowed Users  :</b> <code>{max_uses} person(s)</code>\n"
                        f"├ ⏳ <b>Key Valid For  :</b> <code>{kexp_str}</code>\n"
                        f"├ ⌛ <b>Credit Duration:</b> <code>{cexp_str}</code>\n"
                        f"╰ 💡 <b>Usage          :</b> <code>/redeem {code}</code> (or reply)\n\n"
                        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                    )
                    bot.reply_to(msg, card, parse_mode="HTML")
                else:
                    bot.reply_to(msg, f"❌ Failed to generate key: {desc}", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(msg, f"❌ Error generating keys: {e}", parse_mode="HTML")

    @bot.message_handler(commands=["keys"])
    def cmd_keys(msg):
        if not check_owner_or_silent_reject(msg):
            return

        active = user_manager.list_active_keys()
        if not active:
            bot.reply_to(msg, "ℹ️ <b>No active unredeemed keys.</b>\nGenerate one with <code>/genkey</code>.", parse_mode="HTML")
            return

        lines = [f"📦 <b>Active Available Keys ({len(active)}):</b>\n"]
        now = time.time()
        for idx, k in enumerate(active[-15:], 1):
            val = k.get('value', 'N/A')
            red_by = k.get('redeemed_by')
            if red_by is None:
                red_by = [k['used_by']] if k.get('used_by') else []
            max_u = k.get('max_uses', 1)
            claims = f"{len(red_by)}/{max_u} used"
            k_exp = k.get('key_expires_at')
            exp_info = ""
            if k_exp:
                rem = max(0, int(k_exp - now))
                exp_info = f" | exp: {rem // 3600}h" if rem >= 3600 else f" | exp: {rem // 60}m"
            c_dur = k.get('credit_duration')
            dur_info = f" | cexp: {c_dur // 3600}h" if c_dur else ""
            lines.append(f"{idx}. <code>{k['code']}</code> ({k['type'].upper()}: {val} | {claims}{exp_info}{dur_info})")

        card = (
            f"╭━━━━〔 🔑 <b>ACTIVE KEYS INVENTORY</b> 〕━━━━╮\n\n"
            + "\n".join(lines) + "\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

    @bot.message_handler(commands=["broadcast", "bc"])
    def cmd_broadcast(msg):
        if not check_owner_or_silent_reject(msg):
            return

        is_reply = bool(msg.reply_to_message)
        broadcast_text = None

        if not is_reply:
            parts = (msg.text or "").strip().split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                bot.reply_to(
                    msg,
                    "⚠️ <b>Usage:</b>\n"
                    "1. <code>/broadcast &lt;message text&gt;</code>\n"
                    "2. Or <b>reply</b> <code>/broadcast</code> to any message/media to broadcast it!",
                    parse_mode="HTML"
                )
                return
            broadcast_text = parts[1].strip()

        all_users = list(user_manager.all_users)
        total_targets = len(all_users)

        if total_targets == 0:
            bot.reply_to(msg, "⚠️ <b>No users registered yet!</b>", parse_mode="HTML")
            return

        mode_name = "Media Message (Copy)" if is_reply else "Text Message"
        status_card = (
            f"╭━━━━〔 📢 <b>BROADCAST INITIATED</b> 〕━━━━╮\n\n"
            f"<blockquote>👥 <b>Target Audience:</b> <code>{total_targets} users</code>\n"
            f"📦 <b>Mode:</b> <code>{mode_name}</code>\n"
            f"⚡ <b>Rate Limit:</b> <code>25 msgs/sec protected</code></blockquote>\n\n"
            f"⏳ <i>Broadcasting in background with live updates...</i>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        status_msg = bot.reply_to(msg, status_card, parse_mode="HTML")

        def broadcast_worker():
            delivered = 0
            failed = 0
            start_bc = time.perf_counter()
            last_edit = 0.0

            for idx, target_id in enumerate(all_users):
                try:
                    if is_reply:
                        bot.copy_message(
                            chat_id=target_id,
                            from_chat_id=msg.chat.id,
                            message_id=msg.reply_to_message.message_id
                        )
                    else:
                        bot.send_message(
                            chat_id=target_id,
                            text=broadcast_text,
                            parse_mode="HTML"
                        )
                    delivered += 1
                except Exception:
                    failed += 1

                processed = delivered + failed
                now = time.time()
                if (now - last_edit >= 1.5) or (processed == total_targets):
                    last_edit = now
                    elapsed = time.perf_counter() - start_bc
                    pct = int((processed / total_targets) * 100) if total_targets else 100
                    bar = make_progress_bar(processed, total_targets)
                    speed = (processed / elapsed) if elapsed > 0 else 0

                    live_text = (
                        f"╭━━━━〔 📢 <b>BROADCASTING LIVE...</b> 〕━━━━╮\n\n"
                        f"<blockquote>📊 <b>Progress:</b> <code>{bar} {pct}% ({processed}/{total_targets})</code>\n"
                        f"⏱ <b>Elapsed:</b> <code>{elapsed:.1f}s</code> (<code>{speed:.1f} msg/s</code>)</blockquote>\n\n"
                        f"╭─ 📈 <b>Real-Time Delivery Stats</b>\n"
                        f"├ ✅ <b>Delivered :</b> <code>{delivered}</code>\n"
                        f"├ ❌ <b>Failed    :</b> <code>{failed}</code>\n"
                        f"╰ 🎯 <b>Remaining :</b> <code>{total_targets - processed}</code>\n\n"
                        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n"
                        f"⏳ <i>Broadcasting live to all registered users...</i>"
                    )
                    try:
                        bot.edit_message_text(
                            live_text,
                            chat_id=msg.chat.id,
                            message_id=status_msg.message_id,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                time.sleep(0.04)

            total_elapsed = time.perf_counter() - start_bc
            success_pct = int((delivered / total_targets) * 100) if total_targets else 0
            final_card = (
                f"╭━━━━〔 🎯 <b>BROADCAST COMPLETED</b> 〕━━━━╮\n\n"
                f"<blockquote>👥 <b>Total Targets:</b> <code>{total_targets} users</code>\n"
                f"⏱ <b>Total Time   :</b> <code>{total_elapsed:.2f}s</code>\n"
                f"📦 <b>Mode         :</b> <code>{mode_name}</code></blockquote>\n\n"
                f"╭─ 📊 <b>Final Delivery Report</b>\n"
                f"├ ✅ <b>Delivered  :</b> <code>{delivered} ({success_pct}%)</code>\n"
                f"├ ❌ <b>Failed     :</b> <code>{failed}</code>\n"
                f"╰ 👨‍💻 <b>Executed By:</b> <b>{DEVELOPER}</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            try:
                bot.edit_message_text(
                    final_card,
                    chat_id=msg.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode="HTML"
                )
            except Exception:
                bot.send_message(msg.chat.id, final_card, parse_mode="HTML")

        threading.Thread(target=broadcast_worker, daemon=True).start()

    @bot.message_handler(commands=["stat", "stats"])
    def cmd_stat(msg):
        if not check_owner_or_silent_reject(msg):
            return

        u_stats = user_manager.get_stats()
        card = (
            f"╭━━━━〔 📊 <b>MASTER SYSTEM ANALYTICS</b> 〕━━━━╮\n\n"
            f"╭─ 👥 <b>User Ecosystem</b>\n"
            f"├ 🌐 <b>Total Registered :</b> <code>{u_stats['total_users']} users</code>\n"
            f"├ 💎 <b>VIP Active Users :</b> <code>{u_stats['active_approved']} members</code>\n"
            f"├ ⚡ <b>Today Active Users:</b> <code>{u_stats['today_active_users']} users</code>\n"
            f"╰ 🎯 <b>Today's Bypasses  :</b> <code>{u_stats['today_bypasses']} bypasses</code>\n\n"
            f"╭─ 🚀 <b>Bypass Engine Throughput</b>\n"
            f"├ 📦 <b>All-Time Bypasses :</b> <code>{u_stats['total_shortener_bypasses']} total links</code>\n"
            f"╰ 📡 <b>Supported Networks:</b> <code>7 high-speed adapters</code>\n\n"
            f"╭─ 🔑 <b>Key Inventory</b>\n"
            f"├ 📦 <b>Total Keys       :</b> <code>{u_stats['total_keys']}</code>\n"
            f"╰ 🎟 <b>Active Keys      :</b> <code>{u_stats['active_keys']}</code>\n\n"
            f"╭─ 👑 <b>System Identity</b>\n"
            f"├ 👑 <b>Owner ID  :</b> <code>{OWNER_ID}</code>\n"
            f"╰ 👨‍💻 <b>Developer :</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📈 Shortener Counts", callback_data="cb_show"),
            types.InlineKeyboardButton("👥 VIP Users", callback_data="cb_users"),
        )
        bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["show", "shorteners"])
    def cmd_show(msg):
        if not check_owner_or_silent_reject(msg):
            return

        counts = user_manager.get_shortener_counts()
        total = sum(counts.values())

        def fmt_row(name, key, icon):
            c = counts.get(key, 0)
            pct = int((c / total) * 100) if total > 0 else 0
            bar = make_progress_bar(c, total if total > 0 else 1, length=8)
            return f"├ {icon} <b>{name:<15}:</b> <code>{c}</code> ({pct}%)\n│  <code>{bar}</code>"

        rows = [
            fmt_row("arolinks.com", "arolinks", "🌐"),
            fmt_row("vipshort.in", "vipshort", "🔗"),
            fmt_row("vplink.in", "vplink", "⚡"),
            fmt_row("easysky.in", "easysky", "🌌"),
            fmt_row("monteolympus", "monteolympus", "🏛️"),
            fmt_row("shrinkme.click", "shrinkme", "🎯"),
            fmt_row("dupload.net", "dupload", "📦"),
        ]
        breakdown_text = "\n".join(rows)

        card = (
            f"╭━━━━〔 📈 <b>SHORTENER BYPASS METRICS</b> 〕━━━━╮\n\n"
            f"<blockquote>🎯 <b>All-Time Network Bypasses:</b> <code>{total} links</code></blockquote>\n\n"
            f"╭─ 📊 <b>Performance Per Shortener</b>\n"
            f"{breakdown_text}\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="cb_show"))
        bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")

    @bot.message_handler(commands=["users", "viplist"])
    def cmd_users(msg):
        if not check_owner_or_silent_reject(msg):
            return

        vip_list = user_manager.get_approved_list()
        if not vip_list:
            bot.reply_to(msg, "ℹ️ <b>No active VIP subscribers currently.</b>\nUse <code>/add &lt;userid&gt; &lt;days&gt;</code> to grant access.", parse_mode="HTML")
            return

        lines = [f"👥 <b>Active VIP Subscribers ({len(vip_list)}):</b>\n"]
        for idx, u in enumerate(vip_list, 1):
            exp_str = time.strftime('%Y-%m-%d %H:%M', time.gmtime(u['expires_at']))
            time_left = f"{u['days_left']}d" if u['days_left'] > 2 else f"{u['hours_left']}h"
            uname = f"(@{u['username']})" if u['username'] and u['username'] != "N/A" else ""
            lines.append(
                f"{idx}. <code>{u['user_id']}</code> {uname}\n"
                f"   ⏳ <b>{time_left} left</b> (exp: <code>{exp_str} UTC</code>)"
            )

        card = (
            f"╭━━━━〔 💎 <b>VIP SUBSCRIBERS LIST</b> 〕━━━━╮\n\n"
            + "\n".join(lines) + "\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        bot.reply_to(msg, card, parse_mode="HTML")

    # ========================================================
    # CALLBACK HANDLERS
    # ========================================================

    @bot.callback_query_handler(func=lambda call: True)
    def cb_handler(call):
        uid = call.from_user.id
        data = call.data

        if data == "cb_verify_join":
            if check_user_channel_member(uid):
                is_ref, ref_id, unlocked = user_manager.confirm_channel_joined(uid)
                if is_ref and ref_id:
                    try:
                        uname = call.from_user.username
                        ref_uname = f"@{uname}" if uname else f"User <code>{uid}</code>"
                        r_stat = user_manager.get_user_status(ref_id)
                        reward_notice = ""
                        if unlocked:
                            reward_notice = (
                                f"\n\n🎉 <b>CONGRATULATIONS! 5/5 REFERRALS REACHED!</b>\n"
                                f"⚡ You have unlocked <b>6 HOURS OF UNLIMITED BYPASSES</b>!\n"
                                f"🚀 <i>Enjoy zero countdowns and unlimited links!</i>"
                            )
                        else:
                            bar = make_progress_bar(r_stat['referrals_cycle'], 5)
                            reward_notice = (
                                f"\n\n📊 <b>Milestone Progress:</b> <code>{bar} {r_stat['referrals_cycle']}/5</code>\n"
                                f"💡 <i>{r_stat['referrals_needed']} more referral(s) needed for 6h unlimited!</i>"
                            )
                        bot.send_message(
                            ref_id,
                            f"╭━━━━〔 👥 <b>NEW REFERRAL CONFIRMED!</b> 〕━━━━╮\n\n"
                            f"<blockquote>👤 <b>Member Joined:</b> {ref_uname}\n"
                            f"✅ <i>Status: Verified channel member!</i></blockquote>"
                            f"{reward_notice}\n\n"
                            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                bot.answer_callback_query(call.id, "✅ Membership verified! Welcome to MasterBypass!")
                status = user_manager.get_user_status(uid)
                is_owner = user_manager.is_owner(uid)
                if is_owner:
                    badge = "👑 <b>Owner & Developer</b> (Full Root Control)"
                elif status["role"] == "approved":
                    time_text = f"{status['days_left']}d" if status['days_left'] > 2 else f"{status['hours_left']}h"
                    badge = f"💎 <b>VIP Approved Member</b> (Unlimited — {time_text} left)"
                else:
                    badge = f"🆓 <b>Free Tier Member</b> (1 daily free — {status['daily_left']}/1 left | Credits: <b>{status['credits']}</b>)"

                welcome = (
                    f"╭━━━━〔 ⚡ <b>MASTER BYPASS BOT</b> 〕━━━━╮\n\n"
                    f"✅ <b>Channel Membership Confirmed!</b>\n"
                    f"You now have full access to the bypass engine.\n\n"
                    f"╭─ 👤 <b>Your Membership</b>\n"
                    f"╰ {badge}\n\n"
                    f"╭─ 📖 <b>Quick Navigation</b>\n"
                    f"├ 🔗 Send any supported link directly to this chat\n"
                    f"├ 📋 Type <code>/cmds</code> to view all user commands\n"
                    f"╰ 👥 Type <code>/refer</code> to earn free unlimited hours!\n\n"
                    f"╭─ 👨‍💻 <b>Developer</b>\n"
                    f"╰ <b>{DEVELOPER}</b>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                markup = types.InlineKeyboardMarkup(row_width=2)
                dev_handle = DEVELOPER.lstrip("@")
                markup.add(
                    types.InlineKeyboardButton("📋 All Commands", callback_data="cb_cmds"),
                    types.InlineKeyboardButton("👥 Referral Program", callback_data="cb_refer"),
                    types.InlineKeyboardButton("💳 My Plan", callback_data="cb_myplan"),
                    types.InlineKeyboardButton("👨‍💻 Developer Profile", url=f"https://t.me/{dev_handle}"),
                )
                try:
                    bot.edit_message_text(welcome, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
                except Exception:
                    bot.send_message(call.message.chat.id, welcome, reply_markup=markup, parse_mode="HTML")
            else:
                bot.answer_callback_query(call.id, "❌ You haven't joined the channel yet! Please join first.", show_alert=True)

        elif data == "cb_cmds":
            text = (
                f"╭━━━━〔 📋 <b>USER COMMANDS CONSOLE</b> 〕━━━━╮\n\n"
                f"╭─ 🚀 <b>Link Bypassing</b>\n"
                f"├ 🔗 <b>Send any link directly to this chat</b>\n"
                f"╰ ⚡ Automatically skipped in seconds without ads!\n\n"
                f"╭─ 👤 <b>Account & Rewards</b>\n"
                f"├ 💳 <code>/myplan</code> - Check account tier, quota & credits\n"
                f"├ 👥 <code>/refer</code> - Invite friends (5 refers = 6h unlimited!)\n"
                f"├ 🎁 <code>/redeem &lt;code&gt;</code> - Redeem VIP time or credit keys\n"
                f"├ 💰 <code>/credits</code> - Check your bypass credits balance\n"
                f"╰ 📋 <code>/cmds</code> - View this user commands list\n\n"
                f"╭─ 💎 <b>Supported Shorteners</b>\n"
                f"├ <code>arolinks.com</code>, <code>vipshort.in</code>, <code>vplink.in</code>\n"
                f"├ <code>easysky.in</code>, <code>monteolympus.com</code>\n"
                f"╰ <code>shrinkme.click</code>, <code>dupload.net</code>\n\n"
                f"╭─ 👨‍💻 <b>Developer</b>\n"
                f"╰ <b>{DEVELOPER}</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("💳 My Plan", callback_data="cb_myplan"),
                types.InlineKeyboardButton("👥 Referral Link", callback_data="cb_refer")
            )
            try:
                bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)

        elif data == "cb_refer":
            status = user_manager.get_user_status(uid)
            ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
            cycle = status["referrals_cycle"]
            needed = status["referrals_needed"]
            bar = make_progress_bar(cycle, 5)

            card = (
                f"╭━━━━〔 👥 <b>REFERRAL REWARDS PROGRAM</b> 〕━━━━╮\n\n"
                f"<blockquote>🔗 <b>Your Exclusive Referral Link:</b>\n"
                f"<code>{ref_link}</code></blockquote>\n\n"
                f"╭─ 🎁 <b>How it Works</b>\n"
                f"├ 1. Share your link with friends or groups\n"
                f"├ 2. Friend starts the bot and joins our channel\n"
                f"╰ 3. <b>Every 5 referrals unlock 6 HOURS UNLIMITED VIP!</b>\n\n"
                f"╭─ 📊 <b>Your Referral Metrics</b>\n"
                f"├ 👥 <b>Total Referred  :</b> <code>{status['referral_count']} users</code>\n"
                f"├ 🎯 <b>Current Cycle   :</b> <code>{bar} {cycle}/5</code>\n"
                f"╰ ⏳ <b>Needed for Reward:</b> <code>{needed} more referral(s)</code>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            share_url = f"https://t.me/share/url?url={ref_link}&text=Bypass%20all%20link%20shorteners%20instantly%20with%20zero%20ads%20and%20countdowns!"
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🚀 Share Referral Link", url=share_url),
                types.InlineKeyboardButton("💳 Check My Plan", callback_data="cb_myplan"),
            )
            try:
                bot.edit_message_text(card, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, card, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)

        elif data == "cb_myplan":
            status = user_manager.get_user_status(uid)
            is_owner = user_manager.is_owner(uid)
            dev_handle = DEVELOPER.lstrip("@")
            markup = types.InlineKeyboardMarkup(row_width=1)

            if is_owner:
                card = (
                    f"╭━━━━〔 👑 <b>OWNER PROFILE</b> 〕━━━━╮\n\n"
                    f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                    f"🎖️ <b>Tier:</b> <code>System Owner & Developer</code>\n"
                    f"⚡ <b>Bypasses:</b> <code>Unlimited ∞</code>\n"
                    f"📡 <b>Telemetry:</b> <code>Full Raw Terminal Stream</code>\n"
                    f"🛡️ <b>Privileges:</b> <code>Complete Root Administration</code></blockquote>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                markup.add(types.InlineKeyboardButton("👑 Owner Root Console", callback_data="cb_stat"))
            elif status["role"] == "approved":
                exp_date = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(status['expires_at']))
                time_left_str = f"{status['days_left']} days" if status['days_left'] > 2 else f"{status['hours_left']} hours"
                card = (
                    f"╭━━━━〔 💎 <b>VIP MEMBER PROFILE</b> 〕━━━━╮\n\n"
                    f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                    f"🎖️ <b>Tier:</b> <code>Approved VIP Subscriber</code>\n"
                    f"⚡ <b>Bypasses:</b> <code>Unlimited Daily Access</code>\n"
                    f"⏳ <b>Time Left:</b> <code>{time_left_str}</code>\n"
                    f"📅 <b>Expires At:</b> <code>{exp_date}</code>\n"
                    f"💰 <b>Credits Reserve:</b> <code>{status['credits']} credits</code></blockquote>\n\n"
                    f"🚀 <i>Enjoy zero countdowns and priority high-speed bypassing!</i>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                markup.add(types.InlineKeyboardButton("👨‍💻 Contact Support", url=f"https://t.me/{dev_handle}"))
            else:
                used = status.get("daily_used", 0)
                left = status.get("daily_left", 1)
                bar = "🟩" if left > 0 else "🟥"
                ref_bar = make_progress_bar(status['referrals_cycle'], 5)
                card = (
                    f"╭━━━━〔 🆓 <b>FREE TIER PROFILE</b> 〕━━━━╮\n\n"
                    f"<blockquote>🆔 <b>User ID:</b> <code>{uid}</code>\n"
                    f"🎖️ <b>Tier:</b> <code>Free Member</code>\n"
                    f"🎯 <b>Daily Free Quota:</b> <code>1 bypass / day</code>\n"
                    f"📊 <b>Quota Status:</b> <code>{bar} {used}/1 Used ({left} Left)</code>\n"
                    f"💰 <b>Credits Balance:</b> <code>{status['credits']} credits</code>\n"
                    f"👥 <b>Referral Progress:</b> <code>{ref_bar} {status['referrals_cycle']}/5</code></blockquote>\n\n"
                    f"╭─ ⚡ <b>Unlock Unlimited VIP</b>\n"
                    f"├ 🚀 Invite 5 friends via <code>/refer</code> (get 6h unlimited!)\n"
                    f"├ 🎁 Redeem gift keys via <code>/redeem</code>\n"
                    f"╰ 💬 <b>DM {DEVELOPER} for permanent VIP access!</b>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                markup.add(
                    types.InlineKeyboardButton("👥 Referral Program", callback_data="cb_refer"),
                    types.InlineKeyboardButton(f"💬 DM {DEVELOPER} for VIP", url=f"https://t.me/{dev_handle}")
                )

            try:
                bot.edit_message_text(card, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, card, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)

        elif data == "cb_stat":
            if not user_manager.is_owner(uid):
                return
            u_stats = user_manager.get_stats()
            card = (
                f"╭━━━━〔 📊 <b>MASTER SYSTEM ANALYTICS</b> 〕━━━━╮\n\n"
                f"╭─ 👥 <b>User Ecosystem</b>\n"
                f"├ 🌐 <b>Total Registered :</b> <code>{u_stats['total_users']} users</code>\n"
                f"├ 💎 <b>VIP Active Users :</b> <code>{u_stats['active_approved']} members</code>\n"
                f"├ ⚡ <b>Today Active Users:</b> <code>{u_stats['today_active_users']} users</code>\n"
                f"╰ 🎯 <b>Today's Bypasses  :</b> <code>{u_stats['today_bypasses']} bypasses</code>\n\n"
                f"╭─ 🚀 <b>Bypass Engine Throughput</b>\n"
                f"├ 📦 <b>All-Time Bypasses :</b> <code>{u_stats['total_shortener_bypasses']} total links</code>\n"
                f"╰ 📡 <b>Supported Networks:</b> <code>7 high-speed adapters</code>\n\n"
                f"╭─ 🔑 <b>Key Inventory</b>\n"
                f"├ 📦 <b>Total Keys       :</b> <code>{u_stats['total_keys']}</code>\n"
                f"╰ 🎟 <b>Active Keys      :</b> <code>{u_stats['active_keys']}</code>\n\n"
                f"╭─ 👑 <b>System Identity</b>\n"
                f"├ 👑 <b>Owner ID  :</b> <code>{OWNER_ID}</code>\n"
                f"╰ 👨‍💻 <b>Developer :</b> <b>{DEVELOPER}</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("📈 Shortener Counts", callback_data="cb_show"),
                types.InlineKeyboardButton("👥 VIP Users", callback_data="cb_users"),
            )
            try:
                bot.edit_message_text(card, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, card, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)

        elif data == "cb_show":
            if not user_manager.is_owner(uid):
                return
            counts = user_manager.get_shortener_counts()
            total = sum(counts.values())

            def fmt_row(name, key, icon):
                c = counts.get(key, 0)
                pct = int((c / total) * 100) if total > 0 else 0
                bar = make_progress_bar(c, total if total > 0 else 1, length=8)
                return f"├ {icon} <b>{name:<15}:</b> <code>{c}</code> ({pct}%)\n│  <code>{bar}</code>"

            rows = [
                fmt_row("arolinks.com", "arolinks", "🌐"),
                fmt_row("vipshort.in", "vipshort", "🔗"),
                fmt_row("vplink.in", "vplink", "⚡"),
                fmt_row("easysky.in", "easysky", "🌌"),
                fmt_row("monteolympus", "monteolympus", "🏛️"),
                fmt_row("shrinkme.click", "shrinkme", "🎯"),
                fmt_row("dupload.net", "dupload", "📦"),
            ]
            breakdown_text = "\n".join(rows)

            card = (
                f"╭━━━━〔 📈 <b>SHORTENER BYPASS METRICS</b> 〕━━━━╮\n\n"
                f"<blockquote>🎯 <b>All-Time Network Bypasses:</b> <code>{total} links</code></blockquote>\n\n"
                f"╭─ 📊 <b>Performance Per Shortener</b>\n"
                f"{breakdown_text}\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="cb_show"),
                types.InlineKeyboardButton("📊 System Stats", callback_data="cb_stat"),
            )
            try:
                bot.edit_message_text(card, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, card, reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)

        elif data == "cb_users":
            if not user_manager.is_owner(uid):
                return
            vip_list = user_manager.get_approved_list()
            if not vip_list:
                bot.answer_callback_query(call.id, "No active VIP subscribers currently.", show_alert=True)
                return

            lines = [f"👥 <b>Active VIP Subscribers ({len(vip_list)}):</b>\n"]
            for idx, u in enumerate(vip_list, 1):
                exp_str = time.strftime('%Y-%m-%d %H:%M', time.gmtime(u['expires_at']))
                time_left = f"{u['days_left']}d" if u['days_left'] > 2 else f"{u['hours_left']}h"
                uname = f"(@{u['username']})" if u['username'] and u['username'] != "N/A" else ""
                lines.append(
                    f"{idx}. <code>{u['user_id']}</code> {uname}\n"
                    f"   ⏳ <b>{time_left} left</b> (exp: <code>{exp_str} UTC</code>)"
                )

            card = (
                f"╭━━━━〔 💎 <b>VIP SUBSCRIBERS LIST</b> 〕━━━━╮\n\n"
                + "\n".join(lines) + "\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            try:
                bot.edit_message_text(card, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            except Exception:
                bot.send_message(call.message.chat.id, card, parse_mode="HTML")
            bot.answer_callback_query(call.id)

    # ========================================================
    # MESSAGE & BYPASS HANDLERS
    # ========================================================

    def handle_link_task(chat_id, user_msg_id, raw_url, user_id):
        start_time = time.perf_counter()

        can_bypass, role, status = user_manager.can_bypass(user_id)
        if not can_bypass:
            dev_handle = DEVELOPER.lstrip("@")
            block_card = (
                f"╭━━━━〔 🚫 <b>DAILY LIMIT REACHED</b> 〕━━━━╮\n\n"
                f"<blockquote>👤 <b>User ID:</b> <code>{user_id}</code>\n"
                f"📊 <b>Daily Quota:</b> <code>1/1 Free Bypass Used Today</code>\n"
                f"💰 <b>Credits:</b> <code>0 credits available</code>\n"
                f"🔄 <b>Quota Resets:</b> <code>Daily at 00:00 UTC</code></blockquote>\n\n"
                f"╭─ 🔒 <b>Free Limit Exceeded</b>\n"
                f"├ 🆓 Free members receive <b>1 bypass per day</b>.\n"
                f"├ 👥 Invite 5 friends via <code>/refer</code> (get 6h unlimited!)\n"
                f"├ 🎁 Redeem gift vouchers via <code>/redeem</code>\n"
                f"╰ 💬 <b>DM {DEVELOPER} to access this bot!</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(f"💬 DM {DEVELOPER} to Access This Bot", url=f"https://t.me/{dev_handle}"),
                types.InlineKeyboardButton("👥 Referral Rewards (Earn VIP)", callback_data="cb_refer"),
                types.InlineKeyboardButton("💳 Check My Plan", callback_data="cb_myplan"),
            )
            bot.send_message(
                chat_id,
                block_card,
                reply_to_message_id=user_msg_id,
                reply_markup=markup,
                parse_mode="HTML"
            )
            return

        is_owner = user_manager.is_owner(user_id)

        if is_owner:
            initial_telemetry = (
                f"📡 👑 <b>Owner Live Terminal:</b>\n"
                f"<pre>[*] Initializing TLS session & persona...</pre>\n\n"
            )
        else:
            initial_telemetry = (
                f"<blockquote>⚙️ <b>Status:</b> <code>Bypassing multi-gate security & countdowns...</code>\n"
                f"🚀 <b>Routing:</b> <code>Direct High-Speed Pipeline</code></blockquote>\n\n"
            )

        initial_text = (
            f"╭━━━━〔 ⚡ <b>BYPASSING IN PROGRESS...</b> 〕━━━━╮\n\n"
            f"<blockquote>🔗 <b>Target Link:</b>\n"
            f"<code>{raw_url}</code></blockquote>\n\n"
            f"{initial_telemetry}"
            f"╭─ 📊 <b>Status</b>\n"
            f"├ ⏳ <b>Elapsed :</b> <code>0.0s</code>\n"
            f"╰ 👨‍💻 <b>Developer:</b> <b>{DEVELOPER}</b>\n\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        status_msg = bot.send_message(
            chat_id,
            initial_text,
            reply_to_message_id=user_msg_id,
            parse_mode="HTML"
        )
        updater = TelegramLiveUpdater(bot, chat_id, status_msg.message_id, raw_url, start_time, is_owner=is_owner, role=role)

        try:
            family, _ = normalize(raw_url)
            final_link = bypass_process(raw_url, status_cb=updater.update)
            user_manager.consume_bypass(user_id, family, role)
            elapsed = time.perf_counter() - start_time
            updater.finish(final_link, elapsed)

            # Silent Log Channel dispatch (-1004150412297) - Only owner sees bypassed destination
            try:
                prof = user_manager.user_profiles.get(str(user_id), {})
                uname_val = prof.get("username", "N/A")
                user_tag = f"@{uname_val}" if uname_val and uname_val != "N/A" else "No Username"
                log_card = (
                    f"╭━━━━〔 📡 <b>BYPASS DESTINATION LOG</b> 〕━━━━╮\n\n"
                    f"<blockquote>👤 <b>User:</b> {user_tag}\n"
                    f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"⚡ <b>Engine:</b> <code>{family}</code>\n"
                    f"⏱ <b>Time:</b> <code>{elapsed:.2f}s</code></blockquote>\n\n"
                    f"╭─ 🔗 <b>Original Shortener Link</b>\n"
                    f"╰ <code>{raw_url}</code>\n\n"
                    f"╭─ 🎯 <b>Bypassed Destination URL / File</b>\n"
                    f"╰ <code>{final_link}</code>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                log_markup = types.InlineKeyboardMarkup()
                if final_link and final_link.startswith("http"):
                    log_markup.add(types.InlineKeyboardButton("🚀 Open Destination", url=final_link))
                bot.send_message(LOG_CHANNEL_ID, log_card, reply_markup=log_markup, parse_mode="HTML")
            except Exception:
                pass
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            updater.error(str(e), elapsed)
            try:
                user_tag = f"@{user_id}"
                fail_alert = (
                    f"╭━━━━〔 ⚠️ <b>BYPASS FAILED ALERT</b> 〕━━━━╮\n\n"
                    f"<blockquote>👤 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🔗 <b>Link:</b> <code>{raw_url}</code>\n"
                    f"❌ <b>Error:</b> <code>{str(e)[:150]}</code></blockquote>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                bot.send_message(OWNER_ID, fail_alert, parse_mode="HTML")
            except Exception:
                pass

    @bot.message_handler(func=lambda m: True)
    def handle_all_messages(msg):
        text = (msg.text or "").strip()
        if not text or text.startswith("/"):
            return

        user_id = msg.from_user.id if msg.from_user else msg.chat.id
        username = msg.from_user.username if msg.from_user else None
        user_manager.register(user_id, username)

        # Force Join verification
        if not check_user_channel_member(user_id):
            card, markup = get_force_join_card()
            bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
            return

        # Check if message contains a redeem key or if user replied/sent a key directly
        candidate_keys = user_manager.find_available_keys_in_text(user_id, text)
        if candidate_keys:
            key_code = candidate_keys[0]
            ok, res_text, entry = user_manager.redeem_key(user_id, key_code)
            if ok:
                card = (
                    f"╭━━━━〔 🎁 <b>REDEEM SUCCESSFUL</b> 〕━━━━╮\n\n"
                    f"<blockquote>🔑 <b>Redeemed Key:</b> <code>{key_code}</code></blockquote>\n\n"
                    f"{res_text}\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💳 Check My Plan", callback_data="cb_myplan"))
                bot.reply_to(msg, card, reply_markup=markup, parse_mode="HTML")
                return
        elif text.upper().startswith("VIP-") and len(text.split()) == 1:
            ok, res_text, entry = user_manager.redeem_key(user_id, text.upper())
            bot.reply_to(msg, res_text, parse_mode="HTML")
            return

        tokens = text.split()
        target_link = None

        for token in tokens:
            if token.lower().startswith(("http://", "https://", "ftp://")) or "." in token:
                if any(x in token.lower() for x in ("http", "www.", ".com", ".in", ".net", ".click", ".xyz", ".org", ".io", ".me")):
                    target_link = token
                    break

        if not target_link:
            if len(tokens) == 1 and ("." in tokens[0] or len(tokens[0]) >= 4):
                target_link = tokens[0]
            else:
                bot.reply_to(
                    msg,
                    "⚠️ <b>Invalid Link!</b>\n\nPlease send a valid shortener link (e.g. <code>https://arolinks.com/...</code>).",
                    parse_mode="HTML"
                )
                return

        # Check if shortener is supported
        family, short = normalize(target_link)
        if family is None:
            # 1. Message to user
            dev_handle = DEVELOPER.lstrip("@")
            user_msg = (
                f"╭━━━━〔 ⚠️ <b>LINK NOT AVAILABLE</b> 〕━━━━╮\n\n"
                f"<blockquote>🔗 <b>Link:</b>\n"
                f"<code>{target_link}</code></blockquote>\n\n"
                f"╭─ ℹ️ <b>Bypass Unavailable</b>\n"
                f"├ ❌ <i>This link bypass is currently not available!</i>\n"
                f"╰ 💬 If you want this link bypass added, let owner know: <b>{DEVELOPER}</b>\n\n"
                f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"💬 Request Link to {DEVELOPER}", url=f"https://t.me/{dev_handle}"))
            bot.reply_to(msg, user_msg, reply_markup=markup, parse_mode="HTML")

            # 2. INSTANT ALERT TO OWNER (6021047784)
            try:
                user_tag = f"@{username}" if username else "No Username"
                owner_alert = (
                    f"╭━━━━〔 🚨 <b>UNSUPPORTED LINK ALERT</b> 〕━━━━╮\n\n"
                    f"<blockquote>👤 <b>User:</b> {user_tag}\n"
                    f"🆔 <b>UID:</b> <code>{user_id}</code>\n"
                    f"🔗 <b>Attempted Link:</b>\n"
                    f"<code>{target_link}</code></blockquote>\n\n"
                    f"⚠️ <i>A user tried to bypass an unsupported shortener!</i>\n\n"
                    f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯"
                )
                bot.send_message(OWNER_ID, owner_alert, parse_mode="HTML")
            except Exception:
                pass
            return

        threading.Thread(
            target=handle_link_task,
            args=(msg.chat.id, msg.message_id, target_link, user_id),
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
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("[*] Webhook cleared & pending updates flushed", flush=True)
    except Exception as e:
        print(f"[!] Webhook cleanup note: {e}", flush=True)

    print(f"[*] MasterBypass Telegram Bot started successfully!")
    print(f"[*] Developer: {DEVELOPER}")
    print(f"[*] Listening for incoming messages...\n", flush=True)

    while True:
        try:
            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=20,
                logger_level=logging.INFO,
                allowed_updates=["message", "edited_message", "callback_query", "chat_member", "my_chat_member"],
                restart_on_change=False
            )
        except Exception as e:
            print(f"[!] Polling restart due to error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
