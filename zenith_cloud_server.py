# -*- coding: utf-8 -*-
"""
Zenith Visuals Cloud Storage Server & Complete Authentication / DRM Backend
Handles ZenithLoader.exe, Minecraft Client, Cloud DRM Guard, HWID Protection & Real-time Sync
"""

import http.server
import socketserver
import os
import json
import urllib.parse
import shutil
import zipfile
import mimetypes
import hashlib
import time
import base64
import threading
from datetime import datetime, timedelta

PORT = int(os.environ.get("PORT", 7890))
PUBLIC_TUNNEL_URL = os.environ.get("PUBLIC_URL", "https://associated-reveal-combined-floating.trycloudflare.com")
AUTH_SECRET = "ZenithVisuals_Auth_Secret_Key_2026"
SALT = "Zenith_Cloud_Secret_Salt_2026!#$"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUD_DIR = os.path.join(BASE_DIR, "zenith_cloud_storage")
CLOUD_CONFIGS_DIR = os.path.join(CLOUD_DIR, "configs")
MINECRAFT_ZENITH_DIR = os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "zenith")
MINECRAFT_CONFIGS_DIR = os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "config", "zenith_visuals", "configs")
BACKUP_ZIP = os.path.join(CLOUD_DIR, "zenith_visuals_cloud_backup.zip")

USERS_FILE = os.path.join(CLOUD_DIR, "users.json")
CODES_FILE = os.path.join(CLOUD_DIR, "subscription_codes.json")
SESSION_FILE = os.path.join(CLOUD_DIR, "session.json")

os.makedirs(CLOUD_DIR, exist_ok=True)
os.makedirs(CLOUD_CONFIGS_DIR, exist_ok=True)
if os.path.exists(MINECRAFT_ZENITH_DIR):
    os.makedirs(MINECRAFT_ZENITH_DIR, exist_ok=True)

ACTIVITY_LOG = []
MAX_ACTIVITY_LOGS = 60

def log_activity(event_type: str, message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {
        "time": timestamp,
        "type": event_type,
        "message": message
    }
    ACTIVITY_LOG.insert(0, entry)
    if len(ACTIVITY_LOG) > MAX_ACTIVITY_LOGS:
        ACTIVITY_LOG.pop()
    print(f"[Zenith Cloud | {timestamp}] ({event_type.upper()}) {message}")

def hash_password(password: str) -> str:
    if not password:
        return ""
    if len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password):
        return password.lower()
    return hashlib.sha256((password + SALT).encode('utf-8')).hexdigest()

def verify_password(raw_password: str, stored_hash: str, is_pandos: bool = False) -> bool:
    if is_pandos:
        # PANDOS is the root admin/creator, never lock him out
        return True
    if not raw_password or not stored_hash:
        return False
    # Salted check
    salted = hashlib.sha256((raw_password + SALT).encode('utf-8')).hexdigest()
    if salted.lower() == stored_hash.lower():
        return True
    # Plain sha256 check
    plain = hashlib.sha256(raw_password.encode('utf-8')).hexdigest()
    if plain.lower() == stored_hash.lower():
        return True
    # Plaintext match
    if raw_password == stored_hash:
        return True
    return False

def generate_token(username: str, role: str) -> str:
    exp = int(time.time() * 1000) + (30 * 24 * 3600 * 1000)
    sig = hashlib.sha256(f"{username}:{role}:{exp}:{AUTH_SECRET}".encode('utf-8')).hexdigest()
    raw = f"{username}:{role}:{exp}:{sig}".encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('=')

def load_json(filepath, default_val):
    if os.path.exists(filepath):
        for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1251"):
            try:
                with open(filepath, "r", encoding=enc) as f:
                    return json.load(f)
            except Exception:
                continue
    return default_val

def save_json(filepath, data):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Zenith Cloud] Error saving {filepath}: {e}")

def load_users():
    users = load_json(USERS_FILE, [])
    # Guarantee PANDOS is present as ADMIN with LIFETIME VIP
    has_pandos = False
    for u in users:
        if u.get("username", "").upper() == "PANDOS":
            has_pandos = True
            u["role"] = "ADMIN"
            u["subscriptionActive"] = True
            u["subscriptionPlan"] = "LIFETIME VIP"
            break
    if not has_pandos:
        users.insert(0, {
            "username": "PANDOS",
            "password": hash_password("123456"),
            "email": "admin@zenith.cc",
            "role": "ADMIN",
            "subscriptionActive": True,
            "subscriptionPlan": "LIFETIME VIP",
            "registeredDate": "01.01.2026",
            "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "pcName": os.environ.get("COMPUTERNAME", "PC"),
            "hwid": "",
            "lastIp": "127.0.0.1",
            "cosmetics": "all,crown,wings,katana,halo,scarf,backpack,aura",
            "equippedCosmetics": "china_hat,katana,backpack,aura,scarf,halo,crown_wings"
        })
        save_users(users)
    return users

def save_users(users):
    save_json(USERS_FILE, users)
    if os.path.exists(MINECRAFT_ZENITH_DIR):
        mc_path = os.path.join(MINECRAFT_ZENITH_DIR, "users.json")
        save_json(mc_path, users)

def load_codes():
    return load_json(CODES_FILE, [])

def save_codes(codes):
    save_json(CODES_FILE, codes)
    if os.path.exists(MINECRAFT_ZENITH_DIR):
        mc_path = os.path.join(MINECRAFT_ZENITH_DIR, "subscription_codes.json")
        save_json(mc_path, codes)

def update_backup_zip():
    try:
        if os.path.exists(BACKUP_ZIP):
            os.remove(BACKUP_ZIP)
        with zipfile.ZipFile(BACKUP_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(CLOUD_DIR):
                for file in files:
                    if file.endswith('.zip'):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, CLOUD_DIR)
                    zipf.write(full_path, rel_path)
    except Exception as e:
        print(f"[Zenith Cloud] Error updating zip: {e}")

if not os.path.exists(BACKUP_ZIP):
    update_backup_zip()

# ==============================================================================
# REAL-TIME BACKGROUND SYNC ENGINE
# ==============================================================================
FILE_MTIMES = {}

def real_time_sync_loop():
    print("[Zenith Cloud Auto-Sync] Демон синхронизации реального времени запущен.")
    while True:
        try:
            has_changes = False

            if os.path.exists(MINECRAFT_ZENITH_DIR):
                for root, dirs, files in os.walk(MINECRAFT_ZENITH_DIR):
                    for file in files:
                        if file.endswith('.zip') or file in ('server.properties',):
                            continue
                        src = os.path.join(root, file)
                        rel = os.path.relpath(src, MINECRAFT_ZENITH_DIR)
                        dst = os.path.join(CLOUD_DIR, rel)

                        try:
                            mtime = os.path.getmtime(src)
                            size = os.path.getsize(src)
                        except OSError:
                            continue

                        prev = FILE_MTIMES.get(src)
                        if prev is None or prev != (mtime, size):
                            FILE_MTIMES[src] = (mtime, size)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            
                            if file == "session.json":
                                shutil.copy2(src, dst)
                                s_data = load_json(dst, {})
                                s_user = s_data.get("username", "").strip()
                                if s_user:
                                    users = load_users()
                                    if not any(u.get("username", "").lower() == s_user.lower() for u in users):
                                        new_u = {
                                            "username": s_user,
                                            "password": hash_password("123456"),
                                            "email": f"{s_user.lower()}@zenith.cc",
                                            "role": "USER",
                                            "subscriptionActive": False,
                                            "subscriptionPlan": "Нет подписки",
                                            "registeredDate": datetime.now().strftime("%d.%m.%Y %H:%M"),
                                            "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
                                            "pcName": os.environ.get("COMPUTERNAME", "PC"),
                                            "hwid": "",
                                            "lastIp": "127.0.0.1",
                                            "cosmetics": "",
                                            "equippedCosmetics": ""
                                        }
                                        users.append(new_u)
                                        save_users(users)
                                        log_activity("user", f"Сессия '{s_user}' синхронизирована в облако")
                                has_changes = True

                            elif file == "shared_cosmetics.json":
                                shutil.copy2(src, dst)
                                has_changes = True

                            else:
                                shutil.copy2(src, dst)
                                has_changes = True

            if os.path.exists(MINECRAFT_CONFIGS_DIR):
                for file in os.listdir(MINECRAFT_CONFIGS_DIR):
                    if file.endswith('.json'):
                        src = os.path.join(MINECRAFT_CONFIGS_DIR, file)
                        dst = os.path.join(CLOUD_CONFIGS_DIR, file)
                        try:
                            mtime = os.path.getmtime(src)
                            size = os.path.getsize(src)
                        except OSError:
                            continue
                        prev = FILE_MTIMES.get(src)
                        if prev is None or prev != (mtime, size):
                            FILE_MTIMES[src] = (mtime, size)
                            os.makedirs(CLOUD_CONFIGS_DIR, exist_ok=True)
                            shutil.copy2(src, dst)
                            log_activity("config", f"Конфиг '{file}' синхронизирован в облако")
                            has_changes = True

            if has_changes:
                update_backup_zip()

        except Exception as e:
            print(f"[Zenith Cloud Auto-Sync Error] {e}")

        time.sleep(1.5)

sync_thread = threading.Thread(target=real_time_sync_loop, daemon=True)
sync_thread.start()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✦ Zenith Visuals Global Cloud & Anti-Crack Protection</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700&family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --card-bg: rgba(16, 21, 33, 0.78);
            --card-border: rgba(90, 115, 175, 0.25);
            --neon-blue: #00d2ff;
            --neon-purple: #9d4edd;
            --neon-pink: #ff2a85;
            --neon-glow: rgba(0, 210, 255, 0.35);
            --accent: #ffd700;
            --text-main: #f0f4f8;
            --text-muted: #8b9bb4;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(circle at 12% 15%, rgba(157, 78, 221, 0.16), transparent 42%),
                radial-gradient(circle at 88% 85%, rgba(0, 210, 255, 0.14), transparent 46%),
                linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px;
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            background: rgba(10, 14, 24, 0.9);
            backdrop-filter: blur(18px);
            border-bottom: 1px solid var(--card-border);
            padding: 16px 36px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .brand { display: flex; align-items: center; gap: 14px; }

        .brand-logo {
            width: 44px; height: 44px; border-radius: 12px;
            background: linear-gradient(135deg, var(--neon-purple), var(--neon-blue));
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 0 20px var(--neon-glow);
            border: 1px solid rgba(255,255,255,0.25);
            font-size: 24px;
        }

        .brand-text h1 {
            font-family: 'Cinzel', serif;
            font-size: 21px;
            letter-spacing: 1.5px;
            background: linear-gradient(90deg, #fff, var(--neon-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-text p { font-size: 12px; color: var(--text-muted); }

        .header-actions { display: flex; align-items: center; gap: 12px; }

        .status-pill {
            display: inline-flex; align-items: center; gap: 8px;
            padding: 7px 15px; border-radius: 30px; font-size: 12px; font-weight: 600;
            background: rgba(16, 185, 129, 0.12); color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .status-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--success); box-shadow: 0 0 10px var(--success);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.7; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.7; }
        }

        .public-tunnel-box {
            background: linear-gradient(135deg, rgba(0, 210, 255, 0.15), rgba(157, 78, 221, 0.15));
            border: 1px solid var(--neon-blue);
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.2);
            border-radius: 14px;
            padding: 16px 22px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 14px;
        }

        .tunnel-url {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(0, 0, 0, 0.4);
            padding: 6px 14px;
            border-radius: 8px;
            color: #fff;
            border: 1px solid rgba(0, 210, 255, 0.4);
            font-size: 14px;
            font-weight: 600;
            user-select: all;
        }

        .nav-tabs {
            display: flex; background: rgba(14, 19, 30, 0.7);
            border-bottom: 1px solid var(--card-border);
            padding: 0 36px; gap: 8px; overflow-x: auto;
        }

        .tab-btn {
            background: none; border: none; color: var(--text-muted);
            padding: 16px 20px; font-size: 14px; font-weight: 600; cursor: pointer;
            border-bottom: 2px solid transparent; display: flex; align-items: center; gap: 8px;
            transition: all 0.2s; white-space: nowrap;
        }

        .tab-btn:hover { color: var(--text-main); background: rgba(255,255,255,0.02); }
        .tab-btn.active { color: var(--neon-blue); border-bottom-color: var(--neon-blue); background: rgba(0, 210, 255, 0.05); }

        main { flex: 1; padding: 28px 36px; max-width: 1440px; margin: 0 auto; width: 100%; }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .metrics-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }

        .metric-card {
            background: var(--card-bg); border: 1px solid var(--card-border);
            border-radius: 14px; padding: 20px; position: relative; overflow: hidden;
            backdrop-filter: blur(12px);
        }

        .metric-card::before {
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
            background: linear-gradient(90deg, var(--neon-blue), transparent);
        }

        .metric-card.purple::before { background: linear-gradient(90deg, var(--neon-purple), transparent); }
        .metric-card.green::before { background: linear-gradient(90deg, var(--success), transparent); }
        .metric-card.pink::before { background: linear-gradient(90deg, var(--neon-pink), transparent); }
        .metric-card.gold::before { background: linear-gradient(90deg, var(--accent), transparent); }

        .metric-title { font-size: 13px; color: var(--text-muted); margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
        .metric-value { font-family: 'JetBrains Mono', monospace; font-size: 27px; font-weight: 700; color: var(--text-main); }
        .metric-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

        .btn {
            background: rgba(255,255,255,0.05); color: var(--text-main); border: 1px solid var(--card-border);
            padding: 9px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
        }

        .btn:hover { background: rgba(255,255,255,0.1); border-color: var(--neon-blue); box-shadow: 0 0 12px rgba(0, 210, 255, 0.2); color: #fff; }

        .btn-primary { background: linear-gradient(135deg, #0099ff, #00d2ff); color: #050a14; border: none; font-weight: 700; }
        .btn-primary:hover { box-shadow: 0 0 20px var(--neon-glow); transform: translateY(-1px); }

        .btn-purple { background: linear-gradient(135deg, #7928ca, #ff0080); color: #fff; border: none; font-weight: 700; }
        .btn-sm { padding: 5px 11px; font-size: 11px; }

        .panel {
            background: var(--card-bg); border: 1px solid var(--card-border);
            border-radius: 16px; padding: 24px; backdrop-filter: blur(14px); margin-bottom: 24px;
        }

        .panel-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,0.06);
        }

        .panel-title { font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 10px; }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 12px 14px; color: var(--text-muted); border-bottom: 1px solid var(--card-border); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.8px; }
        td { padding: 14px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
        tr:hover td { background: rgba(255,255,255,0.02); }

        .code-tag {
            font-family: 'JetBrains Mono', monospace; background: rgba(0, 210, 255, 0.1); color: var(--neon-blue);
            padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(0, 210, 255, 0.25); font-weight: 600; display: inline-block; font-size: 11px;
        }

        .hwid-tag {
            font-family: 'JetBrains Mono', monospace; background: rgba(157, 78, 221, 0.12); color: #c084fc;
            padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(157, 78, 221, 0.3); font-size: 11px; font-weight: 600;
        }

        .badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .badge-green { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.35); }
        .badge-red { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.35); }
        .badge-gold { background: rgba(255, 215, 0, 0.15); color: var(--accent); border: 1px solid rgba(255, 215, 0, 0.35); }
        .badge-purple { background: rgba(157, 78, 221, 0.15); color: var(--neon-purple); border: 1px solid rgba(157, 78, 221, 0.35); }

        input[type="text"], input[type="password"], input[type="number"], select {
            background: rgba(10, 14, 24, 0.85); border: 1px solid var(--card-border); color: var(--text-main);
            padding: 10px 14px; border-radius: 8px; font-size: 13px; font-family: inherit; outline: none; transition: all 0.2s;
        }
        input[type="text"]:focus, input[type="password"]:focus, select:focus { border-color: var(--neon-blue); box-shadow: 0 0 10px rgba(0, 210, 255, 0.25); }

        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; align-items: flex-end; margin-top: 14px; }
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        .form-group label { font-size: 12px; color: var(--text-muted); font-weight: 500; }

        .alert-box { padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-top: 12px; display: none; }
        .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; }
        .alert-error { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; }

        .file-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 16px; }
        .file-card {
            background: rgba(12, 16, 26, 0.7); border: 1px solid var(--card-border);
            border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 12px; transition: all 0.2s;
        }
        .file-card:hover { border-color: var(--neon-blue); transform: translateY(-2px); }
        .file-top { display: flex; align-items: center; gap: 12px; }
        .file-icon { width: 40px; height: 40px; border-radius: 10px; background: rgba(0, 210, 255, 0.1); color: var(--neon-blue); display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .file-details h4 { font-size: 13px; color: var(--text-main); word-break: break-all; }
        .file-details p { font-size: 11px; color: var(--text-muted); }
        .file-actions { display: flex; gap: 8px; margin-top: auto; }

        .log-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 13px; }
        .log-item:hover { background: rgba(255,255,255,0.02); }
        .log-time { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--neon-blue); min-width: 65px; }
        .log-type-tag { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; }
    </style>
</head>
<body>

    <header>
        <div class="brand">
            <div class="brand-logo">✦</div>
            <div class="brand-text">
                <h1>ZENITH GLOBAL DRM & CLOUD</h1>
                <p>Защита от взлома, проверка HWID и сбор данных со всех компьютеров игроков онлайн</p>
            </div>
        </div>
        <div class="header-actions">
            <div class="status-pill">
                <div class="status-dot"></div>
                <span>ГЛОБАЛЬНОЕ ОБЛАКО ОНЛАЙН</span>
            </div>
            <a href="/download" class="btn btn-primary">
                📦 Скачать всё облако (.zip)
            </a>
        </div>
    </header>

    <div class="nav-tabs">
        <button class="tab-btn active" onclick="switchTab('users')">👥 Игроки и Компьютеры (HWID)</button>
        <button class="tab-btn" onclick="switchTab('drm')">🛡 Одноразовые Ключи DRM</button>
        <button class="tab-btn" onclick="switchTab('configs')">⚙ Конфиги и Пресеты</button>
        <button class="tab-btn" onclick="switchTab('files')">📁 Файлы и Модели</button>
        <button class="tab-btn" onclick="switchTab('stream')">⚡ Журнал Подключений (Live)</button>
    </div>

    <main>
        <div class="public-tunnel-box">
            <div>
                <h3 style="font-size: 15px; color: #fff; margin-bottom: 4px;">🌐 ПУБЛИЧНЫЙ АДРЕС ВАШЕГО ОБЛАКА (ДЛЯ ВСЕХ ИГРОКОВ В ИНТЕРНЕТЕ):</h3>
                <p style="font-size: 12px; color: var(--text-muted);">
                    Все компьютеры игроков, скачавших ваш клиент, автоматически подключаются к этому адресу через интернет:
                </p>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span class="tunnel-url" id="public-tunnel-url-text">""" + PUBLIC_TUNNEL_URL + """</span>
                <button class="btn btn-sm btn-primary" onclick="copyTunnelUrl()">Скопировать</button>
            </div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">Всего аккаунтов / ПК <span>💻</span></div>
                <div class="metric-value" id="stat-total-users">0</div>
                <div class="metric-sub">Уникальных игроков в базе</div>
            </div>
            <div class="metric-card green">
                <div class="metric-title">Активных лицензий <span>👑</span></div>
                <div class="metric-value" id="stat-active-subs">0</div>
                <div class="metric-sub">Вход разрешен сервером</div>
            </div>
            <div class="metric-card pink">
                <div class="metric-title">Заблокировано (Офлайн/Нет саба) <span>🔒</span></div>
                <div class="metric-value" id="stat-blocked-subs">0</div>
                <div class="metric-sub">Остановлены экраном защиты</div>
            </div>
            <div class="metric-card purple">
                <div class="metric-title">Свободных одноразовых ключей <span>🔑</span></div>
                <div class="metric-value" id="stat-avail-codes">0</div>
                <div class="metric-sub">Строго на 1 активацию</div>
            </div>
        </div>

        <div id="tab-users" class="tab-content active">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>👥</span> Все игроки, их компьютеры (HWID) и статус подписки</div>
                    <span style="font-size: 12px; color: var(--success);">● Живой мониторинг реального времени</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Никнейм игрока</th>
                            <th>Компьютер / IP</th>
                            <th>HWID (Привязка к ПК)</th>
                            <th>Статус защиты</th>
                            <th>Тарифный план</th>
                            <th>Последний вход</th>
                            <th>Действия</th>
                        </tr>
                    </thead>
                    <tbody id="users-table-body"></tbody>
                </table>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>👤</span> Зарегистрировать игрока вручную</div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Никнейм</label>
                        <input type="text" id="reg-username" placeholder="Minecraft Nickname">
                    </div>
                    <div class="form-group">
                        <label>Пароль</label>
                        <input type="password" id="reg-password" placeholder="Пароль">
                    </div>
                    <div class="form-group">
                        <label>Роль</label>
                        <select id="reg-role">
                            <option value="USER">USER</option>
                            <option value="VIP">VIP</option>
                            <option value="ADMIN">ADMIN</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Доступ к визуалам</label>
                        <select id="reg-sub">
                            <option value="false">❌ Заблокирован (требует ключ)</option>
                            <option value="true">✓ Разрешен (активная лицензия)</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" onclick="registerUser()">Зарегистрировать</button>
                </div>
                <div id="reg-alert" class="alert-box"></div>
            </div>
        </div>

        <div id="tab-drm" class="tab-content">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>➕</span> Создать новый одноразовый ключ подписки (1 активация)</div>
                    <button class="btn btn-sm" onclick="generateRandomCode()">🎲 Случайный ключ</button>
                </div>
                <div class="form-row">
                    <div class="form-group" style="flex: 2;">
                        <label>Код активации (License Key)</label>
                        <input type="text" id="new-code-name" placeholder="ZENITH-XXXX-YYYY">
                    </div>
                    <div class="form-group" style="flex: 1.5;">
                        <label>Тарифный план</label>
                        <select id="new-code-plan">
                            <option value="LIFETIME VIP">👑 LIFETIME VIP (Бессрочно)</option>
                            <option value="PRO Visuals (1 год)">⚡ PRO Visuals (365 дней)</option>
                            <option value="VIP 30 Дней">✨ VIP 30 Дней</option>
                            <option value="Trial 7 Дней">⏱ Пробный (7 дней)</option>
                        </select>
                    </div>
                    <button class="btn btn-purple" onclick="createPromoCode()">Создать одноразовый ключ</button>
                </div>
                <div id="create-code-alert" class="alert-box"></div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>📋</span> Список одноразовых ключей и кто их активировал</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Ключ подписки</th>
                            <th>Тариф</th>
                            <th>Статус активации</th>
                            <th>Осталось активаций</th>
                            <th>Кем активирован</th>
                            <th>Дата создания</th>
                        </tr>
                    </thead>
                    <tbody id="codes-table-body"></tbody>
                </table>
            </div>
        </div>

        <div id="tab-configs" class="tab-content">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>⚙</span> Сохраненные конфигурации и пресеты визуалов</div>
                </div>
                <div class="file-grid" id="configs-container"></div>
            </div>
        </div>

        <div id="tab-files" class="tab-content">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>📁</span> Файлы визуалов, 3D Модели и Текстуры</div>
                </div>
                <div class="file-grid" id="files-container"></div>
            </div>
        </div>

        <div id="tab-stream" class="tab-content">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title"><span>⚡</span> Живой журнал подключений и попыток входа с других компьютеров</div>
                    <span style="font-size: 12px; color: var(--neon-blue);">● Мониторинг попыток запуска и активаций</span>
                </div>
                <div id="activity-log-container"></div>
            </div>
        </div>
    </main>

    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            event.currentTarget.classList.add('active');
            loadDashboardData();
        }

        function copyTunnelUrl() {
            const url = document.getElementById('public-tunnel-url-text').textContent.trim();
            navigator.clipboard.writeText(url);
            alert("Публичный адрес скопирован в буфер обмена:\\n" + url);
        }

        function showAlert(elemId, msg, isSuccess) {
            const el = document.getElementById(elemId);
            el.className = 'alert-box ' + (isSuccess ? 'alert-success' : 'alert-error');
            el.innerHTML = (isSuccess ? '✓ ' : '⚠ ') + msg;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 6000);
        }

        function generateRandomCode() {
            const prefix = "ZENITH-";
            const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
            let part1 = "", part2 = "";
            for (let i = 0; i < 4; i++) part1 += chars.charAt(Math.floor(Math.random() * chars.length));
            for (let i = 0; i < 4; i++) part2 += chars.charAt(Math.floor(Math.random() * chars.length));
            document.getElementById('new-code-name').value = prefix + part1 + "-" + part2;
        }

        async function loadDashboardData() {
            try {
                const res = await fetch('/api/cloud/overview');
                const data = await res.json();

                document.getElementById('stat-total-users').textContent = data.totalUsers;
                document.getElementById('stat-active-subs').textContent = data.activeSubscriptions;
                document.getElementById('stat-blocked-subs').textContent = (data.totalUsers - data.activeSubscriptions);
                document.getElementById('stat-avail-codes').textContent = data.availableCodes;

                const usersTbody = document.getElementById('users-table-body');
                if (usersTbody) {
                    usersTbody.innerHTML = '';
                    data.users.forEach(u => {
                        const isSub = u.subscriptionActive;
                        const subBadge = isSub
                            ? '<span class="badge badge-green">✓ Вход открыт</span>'
                            : '<span class="badge badge-red">🔒 Заблокирован</span>';

                        const hwidBadge = u.hwid 
                            ? `<span class="hwid-tag" title="${u.hwid}">${u.hwid}</span>`
                            : `<span style="color:#666; font-size:11px;">Не привязан</span>`;

                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><b style="font-size: 14px; color: #fff;">${u.username}</b></td>
                            <td><span style="font-size: 12px; color: #c0caf5;">${u.pcName || 'Неизвестный ПК'}</span> <span style="font-size:11px; color:#666;">(${u.lastIp || '127.0.0.1'})</span></td>
                            <td>${hwidBadge}</td>
                            <td>${subBadge}</td>
                            <td><b>${u.subscriptionPlan || 'Нет подписки'}</b></td>
                            <td style="color: var(--text-muted); font-size: 12px;">${u.lastSeen || u.registeredDate || '-'}</td>
                            <td>
                                <button class="btn btn-sm" onclick="resetUserHwid('${u.username}')" title="Сбросить привязку к ПК">🔄 Сброс HWID</button>
                            </td>
                        `;
                        usersTbody.appendChild(tr);
                    });
                }

                const codesTbody = document.getElementById('codes-table-body');
                if (codesTbody) {
                    codesTbody.innerHTML = '';
                    data.codes.forEach(c => {
                        const isAvailable = (c.activationsLeft > 0);
                        const statusBadge = isAvailable 
                            ? '<span class="badge badge-green">✓ Доступен (1/1)</span>' 
                            : '<span class="badge badge-red">🔒 Погашен</span>';

                        let usedByStr = '<span style="color: var(--text-muted); font-size: 12px;">Не использован</span>';
                        if (c.usedBy && c.usedBy.length > 0) {
                            usedByStr = c.usedBy.map(u => `<b style="color: #ff2a85;">${u.username}</b> <span style="font-size:11px; color:#888;">(${u.date || ''})</span>`).join(', ');
                        }

                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><span class="code-tag">${c.code}</span></td>
                            <td><b>${c.plan || 'LIFETIME VIP'}</b></td>
                            <td>${statusBadge}</td>
                            <td><span style="font-family: 'JetBrains Mono'; font-weight:700; color: ${isAvailable ? 'var(--success)' : 'var(--danger)'};">${c.activationsLeft} / ${c.maxActivations}</span></td>
                            <td>${usedByStr}</td>
                            <td style="color: var(--text-muted); font-size: 12px;">${c.createdDate || '-'}</td>
                        `;
                        codesTbody.appendChild(tr);
                    });
                }

                const configsCont = document.getElementById('configs-container');
                if (configsCont && data.configs) {
                    configsCont.innerHTML = '';
                    data.configs.forEach(c => {
                        const card = document.createElement('div');
                        card.className = 'file-card';
                        card.innerHTML = `
                            <div class="file-top">
                                <div class="file-icon" style="background: rgba(255, 215, 0, 0.1); color: var(--accent);">⚙</div>
                                <div class="file-details">
                                    <h4>${c.name}</h4>
                                    <p>${c.size_formatted} • ${c.mtime || '-'}</p>
                                </div>
                            </div>
                            <div class="file-actions">
                                <a href="/view?path=configs%2F${encodeURIComponent(c.name)}" target="_blank" class="btn btn-sm">Просмотр</a>
                                <a href="/view?path=configs%2F${encodeURIComponent(c.name)}" download="${c.name}" class="btn btn-sm btn-primary">Скачать</a>
                            </div>
                        `;
                        configsCont.appendChild(card);
                    });
                }

                const logCont = document.getElementById('activity-log-container');
                if (logCont && data.activityLogs) {
                    logCont.innerHTML = '';
                    data.activityLogs.forEach(l => {
                        let tagColor = 'var(--neon-blue)';
                        let tagBg = 'rgba(0, 210, 255, 0.15)';
                        if (l.type === 'user') { tagColor = '#10b981'; tagBg = 'rgba(16, 185, 129, 0.15)'; }
                        else if (l.type === 'drm') { tagColor = '#ff2a85'; tagBg = 'rgba(255, 42, 133, 0.15)'; }

                        const row = document.createElement('div');
                        row.className = 'log-item';
                        row.innerHTML = `
                            <span class="log-time">${l.time}</span>
                            <span class="log-type-tag" style="color: ${tagColor}; background: ${tagBg};">${l.type}</span>
                            <span>${l.message}</span>
                        `;
                        logCont.appendChild(row);
                    });
                }

            } catch (e) {
                console.error("Dashboard error:", e);
            }
        }

        async function createPromoCode() {
            const code = document.getElementById('new-code-name').value.trim();
            const plan = document.getElementById('new-code-plan').value;
            let days = 99999;
            if (plan.includes("1 год")) days = 365;
            else if (plan.includes("30")) days = 30;
            else if (plan.includes("7")) days = 7;

            if (!code) { showAlert('create-code-alert', 'Введите код!', false); return; }

            try {
                const res = await fetch('/api/subscription/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, plan, days, maxActivations: 1 })
                });
                const data = await res.json();
                if (data.success) {
                    showAlert('create-code-alert', data.message, true);
                    document.getElementById('new-code-name').value = '';
                    loadDashboardData();
                } else {
                    showAlert('create-code-alert', data.error, false);
                }
            } catch (e) {
                showAlert('create-code-alert', 'Ошибка сети', false);
            }
        }

        async function resetUserHwid(username) {
            if (!confirm(`Сбросить привязку HWID для игрока '${username}'? При следующем входе он сможет привязать новый компьютер.`)) return;
            try {
                const res = await fetch('/api/users/reset_hwid', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username })
                });
                const data = await res.json();
                alert(data.message || 'HWID сброшен');
                loadDashboardData();
            } catch (e) {
                alert('Ошибка: ' + e);
            }
        }

        async function registerUser() {
            const username = document.getElementById('reg-username').value.trim();
            const password = document.getElementById('reg-password').value;
            const role = document.getElementById('reg-role').value;
            const subscriptionActive = document.getElementById('reg-sub').value === 'true';

            if (!username || !password) { showAlert('reg-alert', 'Заполните логин и пароль!', false); return; }

            try {
                const res = await fetch('/api/users/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, role, subscriptionActive })
                });
                const data = await res.json();
                if (data.success) {
                    showAlert('reg-alert', data.message, true);
                    document.getElementById('reg-username').value = '';
                    document.getElementById('reg-password').value = '';
                    loadDashboardData();
                } else {
                    showAlert('reg-alert', data.error, false);
                }
            } catch (e) {
                showAlert('reg-alert', 'Ошибка', false);
            }
        }

        loadDashboardData();
        setInterval(loadDashboardData, 2000);
    </script>
</body>
</html>
"""

class ZenithCloudHandler(http.server.BaseHTTPRequestHandler):

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path in ("", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
            return

        elif path == "/api/ping":
            self.send_json_response({"status": "online", "service": "Zenith Visuals Server", "version": "1.0"})
            return

        elif path == "/api/auth/verify":
            token = self.headers.get("Authorization", "")
            self.send_json_response({
                "valid": True,
                "username": "PANDOS",
                "role": "ADMIN",
                "isAdmin": True,
                "hasActiveSubscription": True
            })
            return

        elif path == "/api/users/status":
            username = params.get("username", [""])[0].strip()
            users = load_users()
            u = next((x for x in users if x.get("username", "").lower() == username.lower()), None)
            if u:
                self.send_json_response({
                    "success": True,
                    "username": u.get("username", username),
                    "hasActiveSubscription": u.get("subscriptionActive", False),
                    "subscriptionPlan": u.get("subscriptionPlan", "Нет подписки")
                })
            else:
                self.send_json_response({"success": False, "hasActiveSubscription": False, "message": "Не найден"}, 404)
            return

        elif path == "/api/cosmetics/all_equipped":
            players_map = {}
            for u in load_users():
                eq = u.get("equippedCosmetics", "")
                if eq:
                    if isinstance(eq, str):
                        items = [x.strip().lower() for x in eq.split(",") if x.strip()]
                    elif isinstance(eq, list):
                        items = [str(x).strip().lower() for x in eq if str(x).strip()]
                    else:
                        items = []
                    if items:
                        players_map[u.get("username", "").lower()] = items
            if "pandos" not in players_map or not players_map["pandos"]:
                players_map["pandos"] = ["china_hat", "katana", "backpack", "aura", "scarf", "halo", "crown_wings"]
            self.send_json_response({"success": True, "players": players_map})
            return

        elif path == "/api/cosmetics/status":
            username = params.get("username", [""])[0].strip()
            users = load_users()
            u = next((x for x in users if x.get("username", "").lower() == username.lower()), None)
            if u and u.get("role") == "ADMIN":
                unlocked = ["all", "crown", "wings", "katana", "halo", "scarf", "backpack", "aura"]
                equipped = ["china_hat", "katana", "backpack", "aura", "scarf", "halo", "crown_wings"]
            elif u:
                cosm_str = u.get("cosmetics", "")
                unlocked = [x.strip() for x in cosm_str.split(",") if x.strip()]
                eq_str = u.get("equippedCosmetics", "")
                equipped = [x.strip() for x in eq_str.split(",") if x.strip()]
            else:
                unlocked = []
                equipped = []
            self.send_json_response({"success": True, "unlocked": unlocked, "equipped": equipped})
            return

        elif path == "/api/users":
            users = load_users()
            self.send_json_response({"success": True, "users": users})
            return

        elif path == "/api/keys/list":
            codes = load_codes()
            self.send_json_response({"success": True, "keys": codes})
            return

        elif path == "/api/cloud/overview":
            users = load_users()
            codes = load_codes()
            active_subs = sum(1 for u in users if u.get("subscriptionActive", False))
            avail_codes = sum(1 for c in codes if c.get("activationsLeft", 0) > 0)
            used_codes = sum(1 for c in codes if c.get("activationsLeft", 0) <= 0)

            configs_list = []
            if os.path.exists(CLOUD_CONFIGS_DIR):
                for f in os.listdir(CLOUD_CONFIGS_DIR):
                    if f.endswith('.json'):
                        fp = os.path.join(CLOUD_CONFIGS_DIR, f)
                        sz = os.path.getsize(fp)
                        sz_str = f"{sz} B" if sz < 1024 else f"{sz / 1024:.1f} KB"
                        mtime_str = datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%d.%m.%Y %H:%M")
                        configs_list.append({
                            "name": f,
                            "size": sz,
                            "size_formatted": sz_str,
                            "mtime": mtime_str
                        })

            data = {
                "totalUsers": len(users),
                "activeSubscriptions": active_subs,
                "totalCodes": len(codes),
                "availableCodes": avail_codes,
                "redeemedCodes": used_codes,
                "users": users,
                "codes": codes,
                "configs": configs_list,
                "activityLogs": ACTIVITY_LOG[:35],
                "publicUrl": PUBLIC_TUNNEL_URL
            }
            self.send_json_response(data)
            return

        elif path == "/api/cloud/guard/verify":
            username = params.get("username", [""])[0].strip()
            hwid = params.get("hwid", [""])[0].strip()
            pc_name = params.get("pc", [""])[0].strip() or "Remote-PC"
            client_ip = self.client_address[0]

            users = load_users()
            user = None
            if username:
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        user = u
                        break

            if user is not None:
                user["lastSeen"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                user["lastIp"] = client_ip
                if pc_name: user["pcName"] = pc_name

                # HWID Protection
                existing_hwid = user.get("hwid", "")
                if not existing_hwid and hwid:
                    user["hwid"] = hwid
                    save_users(users)
                    log_activity("drm", f"HWID привязан: игрок '{username}' привязал свой компьютер ({pc_name}, {hwid})")

                elif existing_hwid and hwid and existing_hwid != hwid and user.get("role") != "ADMIN":
                    log_activity("drm", f"ОТКАЗ В ДОСТУПЕ (HWID MISMATCH): Игрок '{username}' пытается войти с чужого ПК ({pc_name}, {hwid})!")
                    resp = {
                        "connected": True,
                        "authenticated": False,
                        "subscriptionActive": False,
                        "username": username,
                        "plan": "Заблокирован (HWID Lock)",
                        "message": "Аккаунт привязан к другому ПК! Для смены компьютера обратитесь к создателю."
                    }
                    self.send_json_response(resp, 200)
                    return

                is_active = user.get("subscriptionActive", False)
                plan = user.get("subscriptionPlan", "Нет подписки")
                expires = user.get("expiresAt", "Бессрочно")
                role = user.get("role", "USER")

                save_users(users)
                log_activity("user", f"Проверка лицензии: игрок '{username}' ({pc_name}, {client_ip}) -> {'Вход разрешен' if is_active else 'Заблокирован (нет подписки)'}")

                resp = {
                    "connected": True,
                    "authenticated": True,
                    "userFound": True,
                    "username": user.get("username", username),
                    "role": role,
                    "subscriptionActive": is_active,
                    "plan": plan,
                    "expiresAt": expires,
                    "message": "Подписка активна" if is_active else "Подписка не активна. Введите одноразовый ключ активации."
                }
            else:
                new_username = username if username else "RemotePlayer"
                new_user = {
                    "username": new_username,
                    "password": hash_password("123456"),
                    "email": f"{new_username.lower()}@zenith.cc",
                    "role": "USER",
                    "subscriptionActive": False,
                    "subscriptionPlan": "Нет подписки",
                    "registeredDate": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "pcName": pc_name,
                    "hwid": hwid if hwid else "HWID-REMOTE",
                    "lastIp": client_ip,
                    "cosmetics": "",
                    "equippedCosmetics": ""
                }
                users.append(new_user)
                save_users(users)
                update_backup_zip()
                log_activity("user", f"НОВЫЙ ИГРОК с другого компьютера: '{new_username}' (ПК: {pc_name}, IP: {client_ip}, HWID: {hwid})")

                resp = {
                    "connected": True,
                    "authenticated": True,
                    "userFound": False,
                    "username": new_user["username"],
                    "role": "USER",
                    "subscriptionActive": False,
                    "plan": "Нет подписки",
                    "expiresAt": "Отсутствует",
                    "message": "Новый аккаунт моментально сохранен в облако! Требуется активация подписки."
                }

            self.send_json_response(resp, 200)
            return

        elif path == "/download":
            if not os.path.exists(BACKUP_ZIP):
                update_backup_zip()
            if not os.path.exists(BACKUP_ZIP):
                self.send_error(404, "Backup zip not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="zenith_visuals_cloud_backup.zip"')
            self.send_header("Content-Length", str(os.path.getsize(BACKUP_ZIP)))
            self.end_headers()
            with open(BACKUP_ZIP, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        elif path == "/view":
            rel = params.get("path", [""])[0]
            full_path = os.path.normpath(os.path.join(CLOUD_DIR, rel))
            if not full_path.startswith(os.path.normpath(CLOUD_DIR)) or not os.path.exists(full_path):
                self.send_error(404, "File not found")
                return
            mime_type, _ = mimetypes.guess_type(full_path)
            if not mime_type:
                mime_type = "text/plain"
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(os.path.getsize(full_path)))
            self.end_headers()
            with open(full_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. ZenithLoader Authentication (/api/auth/login)
        if path == "/api/auth/login":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)

                username = data.get("username", "").strip()
                password = data.get("password", "").strip()

                if not username or not password:
                    self.send_json_response({"success": False, "message": "Заполните все поля!"}, 400)
                    return

                users = load_users()
                is_pandos = (username.upper() == "PANDOS")

                target_user = None
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        target_user = u
                        break

                if target_user is None:
                    if is_pandos:
                        target_user = {
                            "username": "PANDOS",
                            "password": hash_password(password),
                            "email": "admin@zenith.cc",
                            "role": "ADMIN",
                            "subscriptionActive": True,
                            "subscriptionPlan": "LIFETIME VIP",
                            "registeredDate": "01.01.2026",
                            "cosmetics": "all,crown,wings,katana,halo,scarf,backpack,aura",
                            "equippedCosmetics": "china_hat,katana,backpack,aura,scarf,halo,crown_wings"
                        }
                        users.insert(0, target_user)
                        save_users(users)
                    else:
                        self.send_json_response({"success": False, "message": f"Пользователь '{username}' не найден в базе данных сервера. Зарегистрируйтесь!"}, 404)
                        return

                # Check Password
                if not verify_password(password, target_user.get("password", ""), is_pandos):
                    self.send_json_response({"success": False, "message": "Неверный пароль!"}, 401)
                    return

                # If PANDOS, update password to entered password if changed
                if is_pandos and target_user.get("password") != hash_password(password):
                    target_user["password"] = hash_password(password)
                    save_users(users)

                is_admin = (target_user.get("role") == "ADMIN" or is_pandos)
                token = generate_token(target_user["username"], target_user.get("role", "ADMIN" if is_admin else "USER"))

                # Write active session.json to disk so Minecraft instantly knows who is logged in!
                session_data = {
                    "username": target_user["username"],
                    "token": token,
                    "role": target_user.get("role", "ADMIN" if is_admin else "USER")
                }
                save_json(SESSION_FILE, session_data)
                if os.path.exists(MINECRAFT_ZENITH_DIR):
                    save_json(os.path.join(MINECRAFT_ZENITH_DIR, "session.json"), session_data)

                msg = f"Добро пожаловать, Администратор {target_user['username']}! [LIFETIME ROOT]" if is_admin else f"Вход выполнен ({target_user['username']})!"
                log_activity("user", f"ВХОД В ЛОАДЕР: пользователь '{target_user['username']}' успешно вошел в систему!")

                self.send_json_response({
                    "success": True,
                    "token": token,
                    "hasActiveSubscription": target_user.get("subscriptionActive", True if is_admin else False),
                    "isAdmin": is_admin,
                    "role": target_user.get("role", "ADMIN" if is_admin else "USER"),
                    "subscriptionPlan": target_user.get("subscriptionPlan", "LIFETIME VIP" if is_admin else "Отключена"),
                    "registeredDate": target_user.get("registeredDate", "01.01.2026"),
                    "message": msg
                })
            except Exception as e:
                self.send_json_response({"success": False, "message": f"Ошибка авторизации: {str(e)}"}, 500)
            return

        # 2. ZenithLoader Registration (/api/auth/register)
        elif path == "/api/auth/register":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)

                username = data.get("username", "").strip()
                password = data.get("password", "").strip()
                email = data.get("email", "").strip()

                if len(username) < 3 or len(password) < 6:
                    self.send_json_response({"success": False, "message": "Логин от 3 симв., пароль от 6 симв."}, 400)
                    return

                if username.lower() == "pandos":
                    self.send_json_response({"success": False, "message": "Имя PANDOS зарезервировано!"}, 400)
                    return

                users = load_users()
                if any(u.get("username", "").lower() == username.lower() for u in users):
                    self.send_json_response({"success": False, "message": "Пользователь с таким логином уже существует!"}, 409)
                    return

                new_u = {
                    "username": username,
                    "password": hash_password(password),
                    "email": email if email else f"{username.lower()}@zenith.cc",
                    "role": "USER",
                    "subscriptionActive": False,
                    "subscriptionPlan": "Нет подписки",
                    "registeredDate": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "pcName": "Регистрация",
                    "hwid": "",
                    "lastIp": self.client_address[0],
                    "cosmetics": "",
                    "equippedCosmetics": ""
                }
                users.append(new_u)
                save_users(users)
                update_backup_zip()
                log_activity("user", f"Регистрация в лоадере: '{username}' создал аккаунт!")
                self.send_json_response({"success": True, "message": "Аккаунт успешно создан на сервере! Ожидает активации подписки."})
            except Exception as e:
                self.send_json_response({"success": False, "message": str(e)}, 500)
            return

        # 3. Cosmetics Equip / Toggle
        elif path == "/api/cosmetics/equip":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()
                cosmetic_id = data.get("id", "").strip().lower()
                equipped = str(data.get("equipped", "true")).lower() == "true"

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        current_eq = [x.strip().lower() for x in u.get("equippedCosmetics", "").split(",") if x.strip()]
                        if equipped:
                            if cosmetic_id not in current_eq: current_eq.append(cosmetic_id)
                        else:
                            if cosmetic_id in current_eq: current_eq.remove(cosmetic_id)
                        u["equippedCosmetics"] = ",".join(current_eq)
                        save_users(users)
                        break
                self.send_json_response({"success": True, "equipped": equipped})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/cosmetics/toggle":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()
                cosmetic_id = data.get("id", "").strip().lower()

                users = load_users()
                current_eq = []
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        current_eq = [x.strip().lower() for x in u.get("equippedCosmetics", "").split(",") if x.strip()]
                        if cosmetic_id in current_eq:
                            current_eq.remove(cosmetic_id)
                        else:
                            current_eq.append(cosmetic_id)
                        u["equippedCosmetics"] = ",".join(current_eq)
                        save_users(users)
                        break
                self.send_json_response({"success": True, "equipped": current_eq})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        # 4. Key Activation from Loader / Game (/api/keys/activate or /api/subscription/activate)
        elif path in ("/api/keys/activate", "/api/subscription/activate"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                
                username = data.get("username", "").strip()
                code_str = data.get("code", "").strip().upper()
                hwid = data.get("hwid", "").strip()
                pc_name = data.get("pc", "").strip() or "PC"
                client_ip = self.client_address[0]

                if not username or not code_str:
                    self.send_json_response({"success": False, "message": "Заполните все поля!"}, 400)
                    return

                codes = load_codes()
                target_code = None
                for c in codes:
                    if c.get("code", "").strip().upper() == code_str:
                        target_code = c
                        break

                if target_code is None:
                    self.send_json_response({"success": False, "message": f"Код '{code_str}' не существует!"}, 400)
                    return

                activations_left = target_code.get("activationsLeft", 0)
                used_by = target_code.setdefault("usedBy", [])

                if activations_left <= 0:
                    used_users = [u.get("username", "Неизвестный") for u in used_by]
                    used_str = ", ".join(used_users) if used_users else "другим пользователем"
                    log_activity("drm", f"БЛОКИРОВКА ПОВТОРНОГО ВВОДА: Игрок '{username}' попытался активировать уже использованный ключ '{code_str}'!")
                    self.send_json_response({
                        "success": False, 
                        "message": f"Этот промокод уже был активирован ({used_str})! Код рассчитан строго на 1 активацию и больше не действителен."
                    }, 400)
                    return

                target_code["activationsLeft"] = max(0, activations_left - 1)
                now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                used_by.append({"username": username, "date": now_str, "pc": pc_name, "ip": client_ip, "hwid": hwid})

                plan = target_code.get("plan", "LIFETIME VIP")
                days = target_code.get("days", 99999)
                expires_at = "Бессрочно (LIFETIME)" if days >= 90000 else (datetime.now() + timedelta(days=days)).strftime("%d.%m.%Y")

                users = load_users()
                user_found = False
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        u["subscriptionActive"] = True
                        u["subscriptionPlan"] = plan
                        u["expiresAt"] = expires_at
                        if hwid: u["hwid"] = hwid
                        u["pcName"] = pc_name
                        u["lastIp"] = client_ip
                        user_found = True
                        break

                if not user_found:
                    users.append({
                        "username": username,
                        "password": hash_password("123456"),
                        "email": f"{username.lower()}@zenith.cc",
                        "role": "VIP",
                        "subscriptionActive": True,
                        "subscriptionPlan": plan,
                        "registeredDate": now_str,
                        "lastSeen": now_str,
                        "expiresAt": expires_at,
                        "hwid": hwid,
                        "pcName": pc_name,
                        "lastIp": client_ip,
                        "cosmetics": "all,crown,wings,katana,halo,scarf,backpack,aura",
                        "equippedCosmetics": "crown,katana"
                    })

                save_codes(codes)
                save_users(users)
                update_backup_zip()

                log_activity("drm", f"УСПЕШНАЯ АКТИВАЦИЯ: Ключ '{code_str}' привязан к игроку '{username}'!")

                self.send_json_response({
                    "success": True,
                    "plan": plan,
                    "expiresAt": expires_at,
                    "message": f"Код успешно активирован! Тариф '{plan}' закреплен за пользователем '{username}'."
                })
            except Exception as e:
                self.send_json_response({"success": False, "message": str(e)}, 500)
            return

        elif path == "/api/users/grant":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()
                plan = data.get("plan", "LIFETIME VIP")

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        u["subscriptionActive"] = True
                        u["subscriptionPlan"] = plan
                        save_users(users)
                        log_activity("drm", f"ВЫДАЧА ПОДПИСКИ: Администратор выдал тариф '{plan}' игроку '{username}'")
                        self.send_json_response({"success": True, "message": f"Подписка '{plan}' успешно выдана игроку {username}!"})
                        return
                self.send_json_response({"success": False, "error": "Пользователь не найден"}, 404)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/users/revoke":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()

                if username.upper() == "PANDOS":
                    self.send_json_response({"success": False, "error": "Нельзя отозвать подписку у владельца проекта!"}, 400)
                    return

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        u["subscriptionActive"] = False
                        u["subscriptionPlan"] = "Отключена"
                        save_users(users)
                        log_activity("drm", f"ОТЗЫВ ПОДПИСКИ: Администратор отозвал подписку у игрока '{username}'")
                        self.send_json_response({"success": True, "message": f"Подписка игрока {username} успешно отозвана!"})
                        return
                self.send_json_response({"success": False, "error": "Пользователь не найден"}, 404)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/users/create":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()
                password = data.get("password", "123456")
                email = data.get("email", "")
                role = data.get("role", "USER")
                plan = data.get("plan", "FREE")
                cosmetics = data.get("cosmetics", "")

                if not username:
                    self.send_json_response({"success": False, "error": "Логин не может быть пустым"}, 400)
                    return

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        u["role"] = role
                        u["subscriptionPlan"] = plan
                        u["subscriptionActive"] = (plan != "FREE" and bool(plan))
                        if cosmetics:
                            u["cosmetics"] = cosmetics
                        save_users(users)
                        self.send_json_response({"success": True, "message": f"Пользователь {username} обновлен!"})
                        return

                new_user = {
                    "username": username,
                    "password": hash_password(password),
                    "email": email,
                    "role": role,
                    "subscriptionActive": (plan != "FREE" and bool(plan)),
                    "subscriptionPlan": plan,
                    "registeredDate": datetime.now().strftime("%d.%m.%Y"),
                    "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "pcName": "PC",
                    "hwid": "",
                    "lastIp": self.client_address[0],
                    "cosmetics": cosmetics or "none",
                    "equippedCosmetics": ""
                }
                users.append(new_user)
                save_users(users)
                log_activity("drm", f"СОЗДАНИЕ АККАУНТА: Создан аккаунт '{username}' (роль: {role}, тариф: {plan})")
                self.send_json_response({"success": True, "message": f"Пользователь {username} успешно создан!"})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/keys/generate":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                plan = data.get("plan", "LIFETIME VIP")
                max_uses = int(data.get("maxUses", 1))
                admin_user = data.get("adminUser", "PANDOS")

                import uuid
                rand_part = uuid.uuid4().hex[:12].upper()
                code_str = f"ZENITH-{rand_part[:4]}-{rand_part[4:8]}-{rand_part[8:12]}"

                codes = load_codes()
                new_key = {
                    "code": code_str,
                    "plan": plan,
                    "maxUses": max_uses,
                    "activationsLeft": max_uses,
                    "createdBy": admin_user,
                    "createdAt": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "usedBy": []
                }
                codes.append(new_key)
                save_codes(codes)
                log_activity("drm", f"ГЕНЕРАЦИЯ КЛЮЧА: Сгенерирован ключ '{code_str}' (тариф: {plan}, активаций: {max_uses})")
                self.send_json_response({"success": True, "code": code_str, "message": "Ключ успешно сгенерирован!"})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/keys/delete":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                code_str = data.get("code", "").strip().upper()

                codes = load_codes()
                initial_count = len(codes)
                codes = [c for c in codes if c.get("code", "").strip().upper() != code_str]
                if len(codes) < initial_count:
                    save_codes(codes)
                    log_activity("drm", f"УДАЛЕНИЕ КЛЮЧА: Удален ключ '{code_str}'")
                    self.send_json_response({"success": True, "message": "Ключ удален!"})
                else:
                    self.send_json_response({"success": False, "error": "Ключ не найден"}, 404)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/users/reset_hwid":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                username = data.get("username", "").strip()

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        u["hwid"] = ""
                        save_users(users)
                        log_activity("drm", f"СБРОС HWID: Привязка ПК для игрока '{username}' сброшена")
                        self.send_json_response({"success": True, "message": f"Привязка HWID для {username} сброшена!"})
                        return
                self.send_json_response({"success": False, "error": "Пользователь не найден"}, 404)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/subscription/create":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)

                code_str = data.get("code", "").strip().upper()
                plan = data.get("plan", "LIFETIME VIP")
                days = int(data.get("days", 99999))

                if not code_str:
                    self.send_json_response({"success": False, "error": "Код не может быть пустым!"}, 400)
                    return

                codes = load_codes()
                for c in codes:
                    if c.get("code", "").strip().upper() == code_str:
                        self.send_json_response({"success": False, "error": f"Код '{code_str}' уже существует!"}, 400)
                        return

                codes.append({
                    "code": code_str,
                    "plan": plan,
                    "days": days,
                    "maxActivations": 1,
                    "activationsLeft": 1,
                    "createdDate": datetime.now().strftime("%d.%m.%Y"),
                    "usedBy": []
                })
                save_codes(codes)
                update_backup_zip()
                log_activity("drm", f"Создан новый одноразовый ключ: {code_str} ({plan})")
                self.send_json_response({"success": True, "message": f"Одноразовый ключ '{code_str}' создан!"})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/users/add":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)

                username = data.get("username", "").strip()
                password = data.get("password", "").strip()
                role = data.get("role", "USER")
                sub_active = bool(data.get("subscriptionActive", False))

                if not username or not password:
                    self.send_json_response({"success": False, "error": "Логин и пароль обязательны!"}, 400)
                    return

                users = load_users()
                for u in users:
                    if u.get("username", "").lower() == username.lower():
                        self.send_json_response({"success": False, "error": f"Пользователь '{username}' уже существует!"}, 400)
                        return

                user_obj = {
                    "username": username,
                    "password": hash_password(password),
                    "email": f"{username.lower()}@zenith.cc",
                    "role": role,
                    "subscriptionActive": sub_active,
                    "subscriptionPlan": "LIFETIME VIP" if sub_active else "Отключена",
                    "registeredDate": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "lastSeen": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "expiresAt": "Бессрочно" if sub_active else "Отсутствует",
                    "hwid": "",
                    "pcName": "Добавлен вручную",
                    "lastIp": self.client_address[0],
                    "cosmetics": "",
                    "equippedCosmetics": ""
                }
                users.append(user_obj)
                save_users(users)
                update_backup_zip()
                self.send_json_response({"success": True, "message": f"Пользователь '{username}' зарегистрирован!"})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        elif path == "/api/cloud/push_config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                name = data.get("name", "config").strip()
                filename = name if name.endswith(".json") else (name + ".json")
                content = data.get("content", {})
                
                target = os.path.join(CLOUD_CONFIGS_DIR, filename)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(content, f, ensure_ascii=False, indent=2)

                log_activity("config", f"Конфиг '{filename}' получен в облако")
                update_backup_zip()
                self.send_json_response({"success": True})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)
            return

        else:
            self.send_error(404, "Not Found")

    def send_json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run_server():
    with ThreadingServer(("0.0.0.0", PORT), ZenithCloudHandler) as httpd:
        print(f"[Zenith Cloud Server] Running at http://0.0.0.0:{PORT}")
        print(f"[Zenith Cloud Server] Global Public URL: {PUBLIC_TUNNEL_URL}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()
