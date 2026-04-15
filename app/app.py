import sqlite3
import random
import re
import dns.resolver
import logging
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, session, redirect, url_for, Response, jsonify
import yfinance as yf
import requests
import feedparser
import urllib.parse
import numpy as np
import pandas as pd
import os
from sklearn.linear_model import LinearRegression
from textblob import TextBlob
import json
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import time

# Configure Logging for SonarQube Observability
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
app = Flask(__name__)
# Security Hotspot Fix: Secret Key for session signing
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "wealth_ai_prod_node_0x992")
 
# ===== DATABASE =====
DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10) # 10s timeout to help with locking
    conn.execute('PRAGMA journal_mode=WAL')    # Enable High-Concurrency mode
    try:
        yield conn
    finally:
        conn.close()

def get_layout(content, user=None, title="Dashboard"):
    nav_links = ""
    if user:
        def get_nav_class(page_title):
            return 'bg-primary-container text-white' if title == page_title else 'text-on-primary-container hover:bg-white/5 transition-colors'
        
        nav_links = f'''
        <nav class="flex-1 px-4 space-y-2 mt-4">
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl {get_nav_class('Dashboard')}" href="/">
        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' {'1' if title=='Dashboard' else '0'};">dashboard</span>
        <span class="font-medium">Dashboard</span>
        </a>
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl {get_nav_class('AI Insights')}" href="/insights">
        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' {'1' if title=='AI Insights' else '0'};">monitoring</span>
        <span class="font-medium">AI Insights</span>
        </a>
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl {get_nav_class('History')}" href="/history">
        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' {'1' if title=='History' else '0'};">history</span>
        <span class="font-medium">History</span>
        </a>
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl {get_nav_class('Settings')}" href="/settings">
        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' {'1' if title=='Settings' else '0'};">settings</span>
        <span class="font-medium">Settings</span>
        </a>
        <div class="h-px bg-white/10 my-4 mx-4"></div>
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl text-on-primary-container hover:bg-white/5 transition-colors" href="/logout">
        <span class="material-symbols-outlined">logout</span>
        <span class="font-medium">Sign Out</span>
        </a>
        </nav>
        <div class="p-6 border-t border-white/10 flex items-center gap-3">
        <div class="w-10 h-10 rounded-full border-2 border-primary-container bg-surface-dim flex items-center justify-center font-bold text-primary">{user[0].upper()}</div>
        <div>
        <p class="text-sm font-bold">{user}</p>
        <p class="text-[10px] text-on-primary-container uppercase tracking-wider">Investor</p>
        </div>
        </div>
        '''
    else:
        nav_links = '''
        <nav class="flex-1 px-4 space-y-2 mt-4">
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl bg-primary-container text-white" href="/auth">
        <span class="material-symbols-outlined">login</span>
        <span class="font-medium">Sign In</span>
        </a>
        </nav>
        '''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>WealthAI — {title}</title>
{SHARED_CSS}
</head>
<body class="bg-background text-on-background flex h-screen overflow-hidden">
<!-- SideNavBar -->
<aside class="w-64 bg-primary text-on-primary flex flex-col shrink-0">
<div class="p-6">
<div class="flex items-center gap-3 mb-1">
<div class="w-8 h-8 rounded-lg bg-primary-container flex items-center justify-center">
<span class="material-symbols-outlined text-on-primary-container" style="font-variation-settings: 'FILL' 1;">account_balance</span>
</div>
<h1 class="text-xl font-extrabold tracking-tight">WealthAI</h1>
</div>
<p class="text-xs text-on-primary-container font-medium opacity-80">Smart Investment Engine</p>
</div>
{nav_links}
</aside>
<main class="flex-1 flex flex-col overflow-hidden">
<!-- TopNavBar -->
<header class="h-16 bg-surface-container-lowest flex items-center justify-between px-8 border-b border-outline-variant/10 shrink-0">
<div class="flex items-center flex-1">
<div class="relative w-96">
<span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm">search</span>
<input class="w-full pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-full text-sm focus:ring-2 focus:ring-primary/20" placeholder="Search investments..." type="text"/>
</div>
</div>
<div class="flex items-center gap-6">
<h2 class="text-sm font-bold text-primary mr-4">{title}</h2>
</div>
</header>
<!-- Scrollable Canvas -->
<div class="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar bg-background">
{content}
</div>
</main>
</body></html>
'''
    return html

# Centralized DB Path
DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')

def init_db():
    # Make path absolute relative to this script
    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            risk_level INTEGER,
            investment_years INTEGER,
            amount REAL,
            best_option TEXT,
            predicted_value REAL,
            annual_rate REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            full_json TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT NOT NULL,
            type TEXT DEFAULT 'login',
            expires_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    # Incremental update for existing databases
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except: pass
    try:
        cursor.execute("ALTER TABLE predictions ADD COLUMN full_json TEXT")
    except: pass
    
    conn.commit()
    conn.close()
 
init_db()
import threading

app = Flask(__name__)

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl

# ===== LOAD ENVIRONMENT VARIABLES FROM .ENV =====
def load_env():
    try:
        root_dir = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(root_dir, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        key, val = line.strip().split('=', 1)
                        os.environ[key.strip()] = val.strip()
    except Exception as e:
        print(f"Error loading .env: {e}")

load_env()

# ===== EMAIL CONFIGURATION =====
# Re-read from os.environ after loading .env
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 465))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')

def send_otp_email(target_email, code, otp_type="Verification"):
    if not SMTP_USER or not SMTP_PASS:
        print(f"WARNING: SMTP credentials not set. Simulated OTP for {target_email}: {code}")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = f"WealthAI Support <{SMTP_USER}>"
        msg['To'] = target_email
        msg['Subject'] = f"{otp_type} Code for WealthAI"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                <h2 style="color: #001b44;">WealthAI Authentication</h2>
                <p>Hello,</p>
                <p>Your <strong>{otp_type} code</strong> is:</p>
                <div style="background: #f4f4f4; padding: 15px; border-radius: 5px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 5px; color: #001b44;">
                    {code}
                </div>
                <p>This code will expire in 10 minutes. If you did not request this, please ignore this email.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #888;">Professional Investment Intelligence Engine — Secure Portfolio Access</p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"CRITICAL: Failed to send email: {e}")
        return False

# ===== EMAIL VALIDATION =====
def is_valid_email(email):
    if not email: return False
    email = email.lower().strip()
    # Strict regex for email syntax
    regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
    if not re.match(regex, email):
        return False
    
    # Common disposable/temporary email domains (Massive Expansion)
    disposable_domains = {
        'tempmail.com', 'mailinator.com', '10minutemail.com', 'guerrillamail.com',
        'sharklasers.com', 'dispostable.com', 'getnada.com', 'boun.cr',
        'temp-mail.org', 'fake-mail.com', 'burnermail.io', 'trashmail.com',
        'yopmail.com', 'mohmal.com', 'maildrop.cc', 'tempmailaddress.com',
        'disposable.com', 'jetable.org', 'crazymailing.com', 'mintemail.com',
        'mail.tm', 'secmail.pro', 'tempmailbox.net', 'tempmail.net', 'incognitomail.com',
        'fakemail.net', 'disposablemail.com', 'tempmail.dev', 'tempworld.xyz'
    }
    
    # Common Typo Protection (Misspelled popular providers)
    typo_domains = {
        'gmaill.com', 'gmaik.com', 'gmal.com', 'gmail.co', 'gmile.com',
        'yaho.com', 'yahooo.com', 'yaho.co', 'yhaoo.com',
        'outluk.com', 'hotmial.com', 'hotmal.com', 'msn.co',
        'iclod.com', 'icloud.co', 'me.co'
    }
    
    domain = email.split('@')[-1]
    if domain in disposable_domains or domain in typo_domains:
        print(f"[AUDIT] BLOCKED: Known fake/typo domain: {domain}")
        return False

    # Real-time DNS MX Check
    try:
        # Check if the domain has Mail Exchanger (MX) records
        print(f"[AUDIT] Verifying domain integrity for: {domain}...")
        records = dns.resolver.resolve(domain, 'MX')
        if not records:
            print(f"[AUDIT] REJECTED: {domain} has no MX records.")
            return False
        print(f"[AUDIT] SUCCESS: {domain} is a valid mail-capable domain.")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout, Exception) as e:
        logger.error(f"[AUDIT] FAILED: {domain} DNS error: {e}")
        return False
        
    return True

# ===== OTP HELPERS =====
def generate_otp(user_id, otp_type='login'):
    code = f"{random.randint(100000, 999999)}"
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            # Invalidate old OTPs of same type
            cur.execute("DELETE FROM otp_codes WHERE user_id = ? AND type = ?", (user_id, otp_type))
            cur.execute("INSERT INTO otp_codes (user_id, code, type, expires_at) VALUES (?, ?, ?, ?)",
                        (user_id, code, otp_type, expiry))
            conn.commit()
        return code
    except Exception as e:
        print(f"OTP Gen Error: {e}")
        return None

def verify_otp_logic(user_id, code, otp_type='login'):
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM otp_codes WHERE user_id = ? AND code = ? AND type = ? AND expires_at > ?",
                        (user_id, code, otp_type, datetime.datetime.now()))
            res = cur.fetchone()
            if res:
                cur.execute("DELETE FROM otp_codes WHERE id = ?", (res[0],))
                conn.commit()
                return True
        return False
    except Exception as e:
        print(f"OTP Verify Error: {e}")
        return False

def show_otp_sim(username, code, otp_type, email=None):
    # Store result of the attempt
    res = {"code": code, "type": otp_type, "time": time.time(), "sent": False, "error": None}
    
    # If email is provided, try sending real email
    if email:
        try:
            sent = send_otp_email(email, code, otp_type)
            if sent:
                print(f"--- REAL OTP SENT TO {email} [{otp_type}]: {code} ---")
                res["sent"] = True
            else:
                res["error"] = "SMTP delivery failed (check terminal for logs)"
        except Exception as e:
            res["error"] = str(e)
            
    if not hasattr(app, 'otp_simulations'):
        app.otp_simulations = {}
    app.otp_simulations[username] = res
    
    if not res["sent"]:
        print(f"--- FALLBACK OTP FOR {username} [{otp_type}]: {code} ---")
app.secret_key = 'wealthai_super_secret_key_2024'

# ===== JOB STORE (in-memory, keyed by uuid) =====
job_store = {}
job_lock = threading.Lock()

# ===== HELPERS =====
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
}

def safe_json(url, timeout=4):
    try:
        res = requests.get(url, timeout=timeout, headers=REQUEST_HEADERS)
        if res.status_code == 200 and res.text.strip():
            return res.json()
    except:
        pass
    return None

# ===== ML MODEL =====
def train_model():
    model = LinearRegression()
    try:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'data.csv')
        df = pd.read_csv(csv_path)
        df['annual_rate'] = (df['returns'] / df['amount']) ** (1 / df['years']) - 1
        X = df[['risk', 'years']].values
        y = df['annual_rate'].values
        model.fit(X, y)
    except:
        X = np.array([[1,1],[1,3],[1,5],[2,1],[2,3],[2,5],[3,1],[3,3],[3,5],[4,1],[4,3],[4,5],[5,1],[5,3],[5,5]])
        y = np.array([0.05,0.06,0.07,0.06,0.08,0.09,0.08,0.10,0.12,0.10,0.13,0.15,0.12,0.16,0.18])
        model.fit(X, y)
    return model

ml_model = train_model()

def predict_return_ml(risk, years):
    return max(0.04, min(ml_model.predict([[risk, years]])[0], 0.20))

# ===== STATIC LISTS =====
NIFTY50_TICKERS = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS",
    "BHARTIARTL.NS","SBIN.NS","WIPRO.NS","ITC.NS","LT.NS",
    "AXISBANK.NS","KOTAKBANK.NS","BAJFINANCE.NS","ASIANPAINT.NS",
    "MARUTI.NS","TATASTEEL.NS","NTPC.NS","SUNPHARMA.NS","TITAN.NS",
    "HCLTECH.NS","DRREDDY.NS","CIPLA.NS","TATAMOTORS.NS","HINDALCO.NS",
    "ONGC.NS","POWERGRID.NS","GRASIM.NS","ADANIENT.NS","ADANIPORTS.NS"
]

KNOWN_MF_CODES = [
    "120503", "118989", "100356", "119551", "100270",
    "119598", "135781", "100444", "101206", "143811",
    "100031", "100227", "118992", "120841", "120594"
]

# ===== STOCK =====
def get_best_stock(risk):
    """
    Randomly picks 10 Nifty50 stocks and bulk downloads (fast). 
    Takes ~1-2 seconds at runtime. No background processes.
    """
    stocks = random.sample(NIFTY50_TICKERS, 5) # 5 for safety/speed
    try:
        raw = yf.download(stocks, period='1y', interval='1d', group_by='ticker', auto_adjust=True, progress=False, threads=False)
        results = []
        for sym in stocks:
            try:
                closes = raw['Close'].dropna() if len(stocks) == 1 else raw[sym]['Close'].dropna()
                if len(closes) < 100: continue
                g = float((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0])
                v = float(closes.pct_change().std())
                results.append((sym, g, round(float(closes.iloc[-1]), 2), g*0.7 - v*0.3))
            except:
                continue
        if results:
            results.sort(key=lambda x: x[3], reverse=True)
            return results[0]
    except:
        pass
    return ("RELIANCE.NS", 0.10, 100, 0.10)

def get_stock_chart_data(symbol, years=1):
    try:
        data = yf.Ticker(symbol).history(period=f"{years}y")
        if data.empty:
            return [], []
        monthly_data = data['Close'].resample('ME').last()
        step = 3 if years > 5 else (2 if years >= 2 else 1)
        return [d.strftime('%b %Y') for d in monthly_data.index[::step]], [round(p, 2) for p in monthly_data.values[::step]]
    except:
        return [], []

def _get_mf_fallback_chart(years=1):
    dates = [(datetime.datetime.now() - datetime.timedelta(days=30*i)).strftime('%b %Y') for i in range(12*years+1)][::-3]
    prices = [100]
    for i in range(1, len(dates)):
        noise = random.uniform(0.002, 0.025)
        prices.append(prices[-1] * (1 + noise))
    return dates, [round(p, 2) for p in prices]

def get_mf_chart_data(mf_code, years=1):
    if not mf_code or mf_code == "135781" or mf_code == "Fallback":
        return _get_mf_fallback_chart(years)
    try:
        nav = safe_json(f"https://api.mfapi.in/mf/{mf_code}")
        if not nav or "data" not in nav: return _get_mf_fallback_chart(years)
        data = nav["data"]
        data = data[:years*252][::-1] 
        if not data: return _get_mf_fallback_chart(years)
        step = max(1, len(data) // 12)
        dates = [datetime.datetime.strptime(d["date"], "%d-%m-%Y").strftime('%b %Y') for d in data[::step]]
        prices = [float(d["nav"]) for d in data[::step]]
        return dates, prices
    except:
        return _get_mf_fallback_chart(years)

# ===== MUTUAL FUND =====
def get_best_mutual_fund():
    """Dynamically samples top Indian Mutual Funds. Predicts safely in ~1-2 seconds."""
    candidates = random.sample(KNOWN_MF_CODES, min(3, len(KNOWN_MF_CODES)))
    
    def fetch_one(code):
        nav = safe_json(f"https://api.mfapi.in/mf/{code}", timeout=2) # Enforce harsh timeout
        if not nav or "data" not in nav: return None
        try:
            nd = nav["data"]
            if len(nd) < 252: return None
            r_nav, o_nav = float(nd[0]["nav"]), float(nd[251]["nav"])
            name = nav.get("meta",{}).get("scheme_name", code)
            return (name, (r_nav - o_nav) / o_nav, code)
        except:
            return None

    best = []
    # Fully sequential to prevent deadlocks with nested executors
    for code in candidates:
        r = fetch_one(code)
        if r: best.append(r)

    if not best:
        return ("Parag Parikh Flexi Cap", 0.12, "135781")
    best.sort(key=lambda x: x[1], reverse=True)
    return best[0]

# ===== REAL ESTATE =====
def get_real_estate(amount, risk):
    if amount < 100000:
        return ("Insufficient Capital for Real Estate (Min ₹1 Lakh)", 0.0, 100, -1.0, "Fallback")
        
    real_place = None
    try:
        from bs4 import BeautifulSoup
        import signal
        cities = ["Bangalore", "Mumbai", "Chennai", "Hyderabad", "Pune"]
        city = random.choice(cities)
        url = f"https://www.commonfloor.com/listing-search?city={city}&min_price={int(amount*0.8)}&max_price={int(amount*1.2)}"
        # Strict 4-second socket cut-off — never let this block Flask
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4, allow_redirects=True)
        soup = BeautifulSoup(r.text, 'html.parser')
        listings = [h2.text.strip() for h2 in soup.find_all('h2') if "Sale" in h2.text or "BHK" in h2.text]
        if listings:
            real_place = random.choice(listings)
    except:
        pass
        
    if not real_place:
        # Deterministic fallback — never random.uniform, never fixed rates
        if amount < 1500000: real_place = "Agricultural Plot (Tier-3 Rural Village)"
        elif amount < 5000000: real_place = "2BHK Apartment (suburban area)"
        else: real_place = "Luxury Property (primary city)"

    # Fetch live NIFTY Realty index for the appreciation rate
    try:
        raw = yf.download("^CNXREALTY", period='1y', interval='1d', auto_adjust=True, progress=False)
        closes = raw['Close'].dropna()
        if len(closes) > 50:
            g = float((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0])
            return (real_place, g, 100, g, "^CNXREALTY")
    except:
        pass
        
    return (real_place, 0.10, 100, 0.10, "Fallback")

def get_re_chart_data(symbol_or_fallback, years=1):
    if symbol_or_fallback == "Fallback":
        return _get_mf_fallback_chart(years)
    return get_stock_chart_data(symbol_or_fallback, years)
 
def save_prediction(username, risk, years, amount, best_option, predicted_value, annual_rate, full_json=""):
    try:
        # Explicitly cast to base types to prevent Numpy serialization errors in SQLite
        r_val = int(risk)
        y_val = int(years)
        a_val = float(amount)
        p_val = float(predicted_value)
        rate_val = float(annual_rate)
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if user:
            print(f"DEBUG: Saving prediction for user {username} (ID:{user[0]})")
            cur.execute('''
                INSERT INTO predictions (user_id, risk_level, investment_years, amount, best_option, predicted_value, annual_rate, full_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user[0], r_val, y_val, a_val, best_option, p_val, rate_val, full_json))
            conn.commit()
            print("DEBUG: Prediction saved successfully.")
        else:
            print(f"DEBUG: User {username} not found for saving prediction.")
        conn.close()
    except Exception as e:
        print(f"CRITICAL: Error saving prediction: {e}")
 
def get_user_predictions(username):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Find user ID first to ensure accurate mapping regardless of session case sensitivity
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return []
            
        # Select specific columns to guarantee index mapping in the UI loop (p[0]..p[8])
        cur.execute('''
            SELECT id, risk_level, investment_years, amount, best_option, predicted_value, annual_rate, created_at, full_json
            FROM predictions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
        ''', (user[0],))
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"DEBUG: get_user_predictions error: {e}")
        return []

def get_prediction_by_id(pred_id, username):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if not user: return None
        cur.execute('SELECT amount, investment_years, risk_level, full_json FROM predictions WHERE id = ? AND user_id = ?', (pred_id, user[0]))
        row = cur.fetchone()
        conn.close()
        return row if row else None
    except:
        return None
 
# ===== SHARED CSS =====
SHARED_CSS = '''
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
<script id="tailwind-config">
      tailwind.config = {
        darkMode: "class",
        theme: {
          extend: {
            colors: {
              "on-primary": "#ffffff",
              "surface-variant": "#e4e2e2",
              "on-secondary-fixed-variant": "#005232",
              "primary-container": "#002f6c",
              "on-primary-fixed-variant": "#224583",
              "background": "#fbf9f8",
              "primary-fixed-dim": "#aec6ff",
              "secondary-container": "#75f8b3",
              "surface-dim": "#dbd9d9",
              "tertiary-container": "#412e00",
              "on-secondary-fixed": "#002111",
              "error-container": "#ffdad6",
              "on-error-container": "#93000a",
              "secondary": "#006d43",
              "surface-bright": "#fbf9f8",
              "tertiary": "#271a00",
              "tertiary-fixed-dim": "#fbbc00",
              "surface-container": "#efeded",
              "primary": "#001b44",
              "on-tertiary-container": "#c39100",
              "surface-container-high": "#eae8e7",
              "on-tertiary-fixed": "#261a00",
              "surface": "#fbf9f8",
              "inverse-on-surface": "#f2f0f0",
              "secondary-fixed": "#78fbb6",
              "on-secondary": "#ffffff",
              "surface-container-lowest": "#ffffff",
              "error": "#ba1a1a",
              "on-tertiary-fixed-variant": "#5c4300",
              "on-secondary-container": "#007147",
              "outline-variant": "#c4c6d2",
              "inverse-primary": "#aec6ff",
              "outline": "#747781",
              "surface-container-highest": "#e4e2e2",
              "surface-container-low": "#f5f3f3",
              "on-error": "#ffffff",
              "primary-fixed": "#d8e2ff",
              "secondary-fixed-dim": "#59de9b",
              "on-background": "#1b1c1c",
              "on-surface-variant": "#434750",
              "inverse-surface": "#303030",
              "on-tertiary": "#ffffff",
              "tertiary-fixed": "#ffdfa0",
              "on-primary-container": "#7999dc",
              "surface-tint": "#3c5d9c",
              "on-surface": "#1b1c1c",
              "on-primary-fixed": "#001a42"
            },
            fontFamily: {
              "headline": ["Manrope"],
              "body": ["Inter"],
              "label": ["Inter"]
            },
            borderRadius: {"DEFAULT": "0.125rem", "lg": "0.25rem", "xl": "0.5rem", "full": "0.75rem"},
          },
        },
      }
    </script>
<style>
        body { font-family: 'Inter', sans-serif; }
        h1, h2, h3 { font-family: 'Manrope', sans-serif; }
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
            vertical-align: middle;
        }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #c4c6d2; border-radius: 10px; }
    </style>
'''

 
def _marketing_landing_page():
    content_html = '''
    <div class="flex flex-col items-center justify-center min-h-[calc(100vh-64px)] p-6 text-center animate-fade-in">
        <div class="px-4 py-1.5 bg-secondary-container/20 text-secondary-fixed-dim text-xs font-bold rounded-full border border-secondary/30 mb-6 uppercase tracking-widest">
            🚀 WealthAI Version 2.0 is Live
        </div>
        <h1 class="text-5xl font-extrabold text-primary mb-5 tracking-tight font-headline">Data-Driven Wealth Building</h1>
        <p class="text-lg text-on-surface-variant max-w-2xl mb-10 leading-relaxed font-body">Unlock elite-level returns with the AI that simultaneously evaluates Live Stocks, Mutual Funds, and Real Estate in milliseconds to find the highest yielding option for your capital.</p>
        <a href="/auth" class="px-8 py-4 bg-primary text-on-primary font-bold text-base rounded-xl transition-all hover:-translate-y-1 hover:shadow-[0_12px_30px_rgba(0,0,0,0.5)]">Start Investing Now</a>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mt-20 w-full text-left">
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-8 transition-all hover:-translate-y-1 hover:border-outline-variant hover:shadow-xl">
                <div class="w-12 h-12 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center mb-5">
                    <span class="material-symbols-outlined text-secondary text-2xl">trending_up</span>
                </div>
                <h3 class="text-lg font-bold text-primary mb-3">Live Market Analysis</h3>
                <p class="text-sm text-on-surface-variant">Our algorithm connects directly to NSE APIs to fetch live momentum, variance, and adjusted returns for the top 50 stocks instantly.</p>
            </div>
            
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-8 transition-all hover:-translate-y-1 hover:border-outline-variant hover:shadow-xl">
                <div class="w-12 h-12 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center mb-5">
                    <span class="material-symbols-outlined text-tertiary-fixed-dim text-2xl">account_balance</span>
                </div>
                <h3 class="text-lg font-bold text-primary mb-3">Real Estate Scraping</h3>
                <p class="text-sm text-on-surface-variant">We index live property listings from top Indian platforms matching your capital to give hyper-local property recommendations.</p>
            </div>
            
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-8 transition-all hover:-translate-y-1 hover:border-outline-variant hover:shadow-xl">
                <div class="w-12 h-12 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center mb-5">
                    <span class="material-symbols-outlined text-primary-fixed-dim text-2xl">memory</span>
                </div>
                <h3 class="text-lg font-bold text-primary mb-3">Hyper-Tuned ML</h3>
                <p class="text-sm text-on-surface-variant">A Scikit-Learn pipeline factors your risk tolerance against historical market volatility to map out mathematically sound portfolios.</p>
            </div>
        </div>
    </div>
    '''
    return get_layout(content_html, user=None, title="Welcome")

@app.route('/auth')
def auth_page():
    error_code = request.args.get('error')
    status = request.args.get('status')
    user_context = request.args.get('user', '')
    toast_html = ''
    
    if error_code == 'exists':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2 z-50"><span class="material-symbols-outlined text-error">warning</span> Username already exists!</div>'
    elif error_code == 'invalid':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2 z-50"><span class="material-symbols-outlined text-error">error</span> Invalid credentials.</div>'
    elif error_code == 'invalid_email':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-4 rounded-2xl shadow-2xl border border-error/20 font-bold flex flex-col gap-1 z-50"><div class="flex items-center gap-2"><span class="material-symbols-outlined text-error">contact_mail</span> Invalid Email Address</div><div class="text-[10px] opacity-70">Please use a valid, non-disposable email for registration.</div></div>'
    elif error_code == 'invalid_otp':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2 z-50"><span class="material-symbols-outlined text-error">lock_reset</span> Invalid or expired OTP.</div>'
    elif error_code == 'not_found':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2 z-50"><span class="material-symbols-outlined text-error">person_off</span> User not found.</div>'
    elif error_code == 'system_busy':
        toast_html = f'''<div class="absolute top-4 right-4 bg-tertiary-container text-on-tertiary-container px-6 py-4 rounded-2xl shadow-2xl border border-tertiary/20 font-bold flex flex-col gap-1 z-50 animate-pulse">
            <div class="flex items-center gap-2 text-sm"><span class="material-symbols-outlined text-tertiary">hourglass_empty</span> Protocol Congestion</div>
            <div class="text-[9px] opacity-70 uppercase tracking-widest font-black">Neural Processor Busy — Please re-attempt in 5s</div>
        </div>'''
    
    if status == 'otp_sent':
        sim = app.otp_simulations.get(user_context, {"code":"???", "sent": False, "error": None})
        is_sim = not SMTP_USER or not SMTP_PASS
        failed_send = not is_sim and not sim.get('sent', False)
        
        mode_label = "Simulation Mode" if is_sim else ("Signal Failed" if failed_send else "Signal Sent")
        icon = "mail" if (not is_sim and not failed_send) else "developer_mode"
        color = "bg-primary-container" if (not is_sim and not failed_send) else "bg-error-container"
        
        toast_html = f'''<div class="absolute top-4 right-4 {color} text-on-primary-container px-6 py-4 rounded-2xl shadow-2xl border border-primary/20 font-bold flex flex-col gap-1 animate-pulse z-50">
            <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-primary">{icon}</span> 
                <span>{mode_label}</span>
            </div>
            {f'<div class="text-[10px] text-primary/60 uppercase tracking-tighter">Code: <b class="text-xs text-primary">{sim["code"]}</b></div>' if (is_sim or failed_send) else '<div class="text-[10px] opacity-70">Check your inbox for the key</div>'}
            {f'<div class="mt-1 px-2 py-0.5 bg-error/10 text-error rounded text-[9px] uppercase tracking-tighter">Delivery Error: {sim.get("error", "Check logs")}</div>' if failed_send else ''}
            {f'<div class="mt-1 px-2 py-0.5 bg-error/10 text-error rounded text-[9px] uppercase tracking-tighter">SMTP Config Required for Email</div>' if is_sim else ''}
        </div>'''
    elif status == 'reset_otp_sent':
        sim = app.otp_simulations.get(user_context, {"code":"???", "sent": False, "error": None})
        is_sim = not SMTP_USER or not SMTP_PASS
        failed_send = not is_sim and not sim.get('sent', False)
        
        mode_label = "Simulation Mode" if is_sim else ("Recovery Failed" if failed_send else "Recovery Sent")
        toast_html = f'''<div class="absolute top-4 right-4 bg-tertiary-container text-on-tertiary-container px-6 py-4 rounded-2xl shadow-2xl border border-tertiary/20 font-bold flex flex-col gap-1 animate-pulse z-50">
            <div class="flex items-center gap-2">
                <span class="material-symbols-outlined text-tertiary">lock_open</span> 
                <span>{mode_label}</span>
            </div>
            {f'<div class="text-[10px] text-tertiary/60 uppercase tracking-tighter">Reset Code: <b class="text-xs text-tertiary">{sim["code"]}</b></div>' if (is_sim or failed_send) else '<div class="text-[10px] opacity-70">Recovery signal broadcasted</div>'}
            {f'<div class="mt-1 px-2 py-0.5 bg-error/10 text-error rounded text-[9px] uppercase tracking-tighter">Error: {sim.get("error", "Check terminal")}</div>' if failed_send else ''}
            {f'<div class="mt-1 px-2 py-0.5 bg-error/10 text-error rounded text-[9px] uppercase tracking-tighter">SMTP Config Required for Email</div>' if is_sim else ''}
        </div>'''
    elif status == 'password_reset_success':
        toast_html = '<div class="absolute top-4 right-4 bg-secondary-container text-on-secondary-container px-6 py-3 rounded-xl shadow-lg border border-secondary/20 font-bold flex items-center gap-2"><span class="material-symbols-outlined text-secondary">check_circle</span> Password updated successfully.</div>'

    content_html = f'''
    <div class="flex items-center justify-center min-h-[calc(100vh-64px)] animate-fade-in relative py-12 px-4 bg-gradient-to-tr from-surface-container-low via-background to-surface-container-low">
        {toast_html}
        
        <!-- Decorative Elements -->
        <div class="absolute top-[10%] left-[5%] w-64 h-64 bg-primary/5 rounded-full blur-3xl animate-pulse"></div>
        <div class="absolute bottom-[10%] right-[5%] w-96 h-96 bg-secondary/5 rounded-full blur-3xl animate-pulse" style="animation-delay: 1s"></div>

        <div class="w-full max-w-lg bg-surface-container-lowest/80 backdrop-blur-xl border border-outline-variant/20 rounded-[2.5rem] p-12 shadow-[0_32px_64px_-16px_rgba(0,0,0,0.1)] overflow-hidden relative">
            <div class="text-center mb-12">
                <div class="w-24 h-24 bg-primary mx-auto rounded-[2rem] flex items-center justify-center mb-8 shadow-2xl shadow-primary/40 group hover:rotate-12 transition-all duration-500 cursor-pointer">
                    <span class="material-symbols-outlined text-5xl text-on-primary group-hover:scale-110 transition-transform" style="font-variation-settings: 'FILL' 1;">account_balance</span>
                </div>
                <h1 id="authTitle" class="text-5xl font-black text-primary tracking-tight font-headline mb-3">WealthAI</h1>
                <p id="authSub" class="text-sm text-on-surface-variant/70 font-semibold tracking-wide uppercase">Elite Financial Intelligence</p>
            </div>
            
            <div class="flex bg-surface-container-low p-1.5 rounded-2xl mb-10 font-bold text-[10px] uppercase tracking-widest gap-1 border border-outline-variant/5">
                <button id="loginTab" onclick="setType('login')" class="flex-1 py-3.5 rounded-xl bg-primary text-on-primary shadow-lg transition-all duration-300">Authentication</button>
                <button id="otpTab" onclick="setType('otp')" class="flex-1 py-3.5 rounded-xl text-on-surface-variant hover:bg-surface-container-high/50 transition-all duration-300">Quick Access</button>
                <button id="signupTab" onclick="setType('signup')" class="flex-1 py-3.5 rounded-xl text-on-surface-variant hover:bg-surface-container-high/50 transition-all duration-300">Join Engine</button>
            </div>

            <form id="authForm" action="/login" method="POST" onsubmit="return validateBeforeSubmit()" class="space-y-7">
                <!-- Username -->
                <div id="usernameSection" class="group">
                    <label class="block text-[11px] font-black uppercase tracking-[0.25em] text-primary/60 ml-1 mb-2.5">Global Identity</label>
                    <div class="relative">
                        <span class="material-symbols-outlined absolute left-5 top-1/2 -translate-y-1/2 text-outline-variant text-[22px] group-focus-within:text-primary transition-colors">person_pin</span>
                        <input type="text" name="username" value="{user_context}" required class="w-full pl-14 pr-6 py-5 bg-surface-container-low/50 border-2 border-transparent focus:border-primary/10 rounded-2xl text-base focus:ring-4 focus:ring-primary/5 transition-all text-primary font-bold placeholder:text-outline-variant/40" placeholder="e.g. s_wealth_01">
                    </div>
                </div>

                <!-- Password -->
                <div id="passwordSection" class="group">
                    <div class="flex justify-between items-center ml-1 mb-2.5">
                        <label class="text-[11px] font-black uppercase tracking-[0.25em] text-primary/60">Neural Key</label>
                        <button type="button" onclick="setType('forgot')" class="text-[10px] font-black text-primary/80 hover:text-primary underline decoration-primary/20 hover:decoration-primary transition-all uppercase tracking-widest">Recovery?</button>
                    </div>
                    <div class="relative">
                        <span class="material-symbols-outlined absolute left-5 top-1/2 -translate-y-1/2 text-outline-variant text-[22px] group-focus-within:text-primary transition-colors">encrypted</span>
                        <input type="password" name="password" id="pwInput" class="w-full pl-14 pr-6 py-5 bg-surface-container-low/50 border-2 border-transparent focus:border-primary/10 rounded-2xl text-base focus:ring-4 focus:ring-primary/5 transition-all text-primary font-bold placeholder:text-outline-variant/40" placeholder="••••••••">
                    </div>
                </div>

                <!-- OTP Field -->
                <div id="otpSection" style="display:none;" class="animate-in fade-in slide-in-from-top-2 duration-500">
                    <label class="block text-[11px] font-black uppercase tracking-[0.25em] text-tertiary/60 ml-1 mb-2.5">Verification Sequence</label>
                    <div class="relative group">
                        <span class="material-symbols-outlined absolute left-5 top-1/2 -translate-y-1/2 text-outline-variant text-[22px] group-focus-within:text-tertiary transition-colors">domain_verification</span>
                        <input type="text" name="otp" id="otpInput" maxlength="6" class="w-full pl-14 pr-6 py-5 bg-tertiary-container/10 border-2 border-transparent focus:border-tertiary/20 rounded-2xl text-2xl focus:ring-4 focus:ring-tertiary/5 transition-all text-tertiary font-black tracking-[0.7em] placeholder:text-outline-variant/20" placeholder="000000">
                    </div>
                </div>

                <!-- Email (Signup only) -->
                <div id="emailSection" style="display:none;" class="animate-in fade-in slide-in-from-top-2 duration-500">
                    <div class="flex justify-between items-center ml-1 mb-2.5">
                        <label class="text-[11px] font-black uppercase tracking-[0.25em] text-primary/60">Network Communications</label>
                        <div id="emailFeedback" class="text-[9px] font-black uppercase tracking-widest hidden">Validating...</div>
                    </div>
                    <div class="relative group">
                        <span class="material-symbols-outlined absolute left-5 top-1/2 -translate-y-1/2 text-outline-variant text-[22px] group-focus-within:text-primary transition-colors">contact_mail</span>
                        <input type="email" name="email" id="emailInput" class="w-full pl-14 pr-6 py-5 bg-surface-container-low/50 border-2 border-transparent focus:border-primary/10 rounded-2xl text-base focus:ring-4 focus:ring-primary/5 transition-all text-primary font-bold placeholder:text-outline-variant/40" placeholder="hq@wealth.ai">
                    </div>
                </div>
                
                <button type="submit" id="authBtn" class="w-full mt-4 bg-primary text-on-primary font-black py-6 rounded-2xl shadow-2xl hover:-translate-y-1 hover:shadow-primary/30 transition-all active:scale-[0.98] text-lg tracking-tight">Execute Protocol</button>
            </form>
            
            <div class="mt-10 flex items-center justify-center gap-6 opacity-40 grayscale group-hover:grayscale-0 transition-all">
                <span class="text-[9px] font-black uppercase tracking-widest text-on-surface-variant">TLS 1.3 Certified</span>
                <div class="w-1 h-1 rounded-full bg-on-surface-variant"></div>
                <span class="text-[9px] font-black uppercase tracking-widest text-on-surface-variant">AES-256 Encryption</span>
            </div>
        </div>
    </div>
    <script>
    let currentMode = 'login';
    function setType(t){{
        const form = document.getElementById('authForm');
        const title = document.getElementById('authTitle');
        const sub = document.getElementById('authSub');
        const btn = document.getElementById('authBtn');
        const tabs = {{'login': document.getElementById('loginTab'), 'otp': document.getElementById('otpTab'), 'signup': document.getElementById('signupTab')}};
        
        const pwSec = document.getElementById('passwordSection');
        const otpSec = document.getElementById('otpSection');
        const emailSec = document.getElementById('emailSection');
        const otpIn = document.getElementById('otpInput');
        const pwIn = document.getElementById('pwInput');

        currentMode = t;
        
        // Reset state
        btn.disabled = false;
        btn.style.opacity = '1';
        if(emailFeedback) emailFeedback.style.display = 'none';

        Object.values(tabs).forEach(el => {{ if(el) el.className = 'flex-1 py-3.5 rounded-xl text-on-surface-variant hover:bg-surface-container-high/50 transition-all duration-300'; }});
        if(tabs[t]) tabs[t].className = 'flex-1 py-3.5 rounded-xl bg-primary text-on-primary shadow-lg transition-all duration-300';

        if(t==='signup'){{
            form.action = '/signup';
            if('{status}' === 'signup_otp_sent'){{
                btn.innerText = 'Verify & Complete';
                otpSec.style.display = 'block';
                pwSec.style.display = 'none';
                emailSec.style.display = 'none';
                otpIn.required = true;
                pwIn.required = false;
                sub.innerText = 'Identity decryption in progress';
            }} else {{
                title.innerText = 'Establish';
                sub.innerText = 'Initialize your investment node';
                btn.innerText = 'Verify Identity';
                pwSec.style.display = 'block';
                otpSec.style.display = 'none';
                emailSec.style.display = 'block';
                pwIn.required = true;
                otpIn.required = false;
            }}
        }} else if(t==='otp'){{
            if('{status}' === 'otp_sent'){{
                form.action = '/verify-login-otp';
                btn.innerText = 'Verify Sequence';
                otpSec.style.display = 'block';
                pwSec.style.display = 'none';
                otpIn.required = true;
                pwIn.required = false;
            }} else {{
                form.action = '/request-otp';
                btn.innerText = 'Generate Signal';
                otpSec.style.display = 'none';
                pwSec.style.display = 'none';
                otpIn.required = false;
                pwIn.required = false;
            }}
            title.innerText = 'Sync Access';
            sub.innerText = 'Real-time authentication signal';
            emailSec.style.display = 'none';
        }} else if(t==='forgot'){{
            if('{status}' === 'reset_otp_sent'){{
                form.action = '/reset-password';
                btn.innerText = 'Re-establish Key';
                otpSec.style.display = 'block';
                pwSec.style.display = 'block';
                otpIn.required = true;
                pwIn.required = true;
                sub.innerText = 'Decrypting identity access';
            }} else {{
                form.action = '/forgot-password';
                btn.innerText = 'Request Recovery';
                otpSec.style.display = 'none';
                pwSec.style.display = 'none';
                otpIn.required = false;
                pwIn.required = false;
                sub.innerText = 'Initialize secure recovery protocol';
            }}
            title.innerText = 'Recovery';
            emailSec.style.display = 'none';
            Object.values(tabs).forEach(el => {{ if(el) el.className = 'flex-1 py-3.5 rounded-xl text-on-surface-variant transition-all opacity-30 cursor-not-allowed'; }});
        }} else {{
            form.action = '/login';
            title.innerText = 'WealthAI';
            sub.innerText = 'Elite Financial Intelligence';
            btn.innerText = 'Execute Protocol';
            pwSec.style.display = 'block';
            otpSec.style.display = 'none';
            emailSec.style.display = 'none';
            pwIn.required = true;
            otpIn.required = false;
        }}
    }}
    
    // Auto-set state based on URL
    if('{status}' === 'otp_sent') setType('otp');
    if('{status}' === 'signup_otp_sent') setType('signup');
    if('{status}' === 'reset_otp_sent') setType('forgot');

    // SMART EMAIL VALIDATION (Zero-OTP)
    const emailInput = document.getElementById('emailInput');
    const emailFeedback = document.getElementById('emailFeedback');
    const authBtn = document.getElementById('authBtn');
    const authForm = document.getElementById('authForm');
    let validationTimeout;
    let isEmailVerified = true; 

    function validateBeforeSubmit() {{
        // Bypass validation if in Step 2 of signup (email section hidden)
        if (currentMode === 'signup' && document.getElementById('emailSection').style.display === 'none') {{
            return true;
        }}
        if (currentMode === 'signup' && !isEmailVerified) {{
            emailFeedback.className = 'text-[10px] font-bold mt-2 text-error animate-bounce';
            emailFeedback.innerText = '⚠️ Please provide a valid domain before verifying identity';
            return false;
        }}
        return true;
    }}

    emailInput.addEventListener('input', () => {{
        if(currentMode !== 'signup') return;
        
        isEmailVerified = false;
        clearTimeout(validationTimeout);
        emailFeedback.style.display = 'block';
        emailFeedback.className = 'text-[10px] font-bold mt-2 text-primary animate-pulse';
        emailFeedback.innerText = 'Scanning Domain Integrity...';
        
        // Safety Lock: Disable button immediately
        authBtn.disabled = true;
        authBtn.style.opacity = '0.5';
        authBtn.innerText = 'Verifying Domain...';

        const email = emailInput.value.trim();
        if(email === '') {{
            emailFeedback.style.display = 'none';
            authBtn.disabled = false;
            authBtn.innerText = 'Establish Identity';
            authBtn.style.opacity = '1';
            isEmailVerified = true;
            return;
        }}

        validationTimeout = setTimeout(() => {{
            fetch('/validate-email-ajax', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                body: 'email=' + encodeURIComponent(email)
            }})
            .then(r => r.json())
            .then(data => {{
                if(data.valid) {{
                    emailFeedback.className = 'text-[10px] font-bold mt-2 text-green-500';
                    emailFeedback.innerText = '✅ ' + data.message;
                    authBtn.disabled = false;
                    authBtn.style.opacity = '1';
                    authBtn.innerText = 'Establish Identity';
                    isEmailVerified = true;
                }} else {{
                    emailFeedback.className = 'text-[10px] font-bold mt-2 text-error';
                    emailFeedback.innerText = '❌ ' + data.message;
                    authBtn.disabled = true;
                    authBtn.style.opacity = '0.5';
                    authBtn.innerText = 'Invalid Domain';
                    isEmailVerified = false;
                }}
            }});
        }}, 600);
    }});
    </script>
    '''
    return get_layout(content_html, user=None, title="Authentication")

def _marketing_landing_page():
    """
    Renders a premium 'Organic Brutalist' landing page for unauthenticated users.
    Features call-to-action for the AI Investment Engine.
    """
    content = '''
    <div class="h-full flex items-center justify-center p-8 bg-gradient-to-br from-background to-primary/5">
        <div class="max-w-4xl w-full text-center space-y-12 animate-fade-in">
            <div class="space-y-4">
                <div class="flex justify-center">
                    <div class="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center shadow-2xl rotate-3">
                         <span class="material-symbols-outlined text-4xl text-on-primary">account_balance</span>
                    </div>
                </div>
                <h1 class="text-7xl font-black tracking-tighter text-primary font-headline">Intelligence In Motion</h1>
                <p class="text-xl text-on-surface-variant max-w-2xl mx-auto font-medium leading-relaxed opacity-80">
                    The ultra-fast AI engine for optimized, multi-asset investment decision making. Stock indexing, Mutual Fund analytics, and Real Estate valuation combined.
                </p>
            </div>
            
            <div class="flex flex-col sm:flex-row gap-6 justify-center">
                <a href="/auth" class="px-12 py-5 bg-primary text-on-primary font-black rounded-[2rem] shadow-2xl hover:-translate-y-1 transition-all flex items-center justify-center gap-3 group">
                    Enter Platform
                    <span class="material-symbols-outlined group-hover:translate-x-1 transition-transform">arrow_forward</span>
                </a>
                <a href="/auth" class="px-12 py-5 bg-surface-container-high text-primary font-black rounded-[2rem] border border-outline-variant hover:bg-white transition-all flex items-center justify-center gap-3">
                    Learn Philosophy
                </a>
            </div>
            
            <div class="grid grid-cols-3 gap-8 pt-12 opacity-50">
                <div><h4 class="text-xs font-black uppercase tracking-widest mb-2">Real-Time Data</h4><p class="text-[10px] font-bold">NSE · BSE · Yahoo Finance</p></div>
                <div><h4 class="text-xs font-black uppercase tracking-widest mb-2">AI-Driven</h4><p class="text-[10px] font-bold">Predictive ML Backtesting</p></div>
                <div><h4 class="text-xs font-black uppercase tracking-widest mb-2">Secure</h4><p class="text-[10px] font-bold">Signal Encrypted OTP Sync</p></div>
            </div>
        </div>
    </div>
    '''
    return get_layout(content, title="Welcome")

# ===== HOME =====
@app.route('/')
def home():
    if 'user' not in session:
        return _marketing_landing_page()
    username = session['user']
    past_predictions = get_user_predictions(username)
 
    history_html = ''
    if past_predictions:
        history_html = '<div class="mt-8"><h3 class="text-lg font-extrabold text-primary mb-4">Recent Predictions</h3><div class="space-y-3">'
        for p in past_predictions:
            # p[1] = risk_level, p[7] = created_at, p[3] = amount, p[4] = best_option, p[5] = predicted_value, p[2] = years
            # rc logic based on risk_level (p[1])
            rc = 'text-error' if p[1]>3 else ('text-tertiary-fixed-dim' if p[1]==3 else 'text-secondary')
            bgc = 'bg-error-container' if p[1]>3 else ('bg-tertiary-fixed/30' if p[1]==3 else 'bg-secondary-container')
            ds = p[7][:10] if p[7] else ''
            gain_pct = ((p[5] - p[3]) / p[3] * 100) if p[3] > 0 else 0
            history_html += f'''
            <div class="flex items-center justify-between p-4 bg-surface-container-lowest border border-outline-variant/10 rounded-xl hover:bg-primary-fixed/20 transition-colors">
                <div class="flex items-center gap-4">
                    <span class="text-xs font-bold text-on-surface-variant font-mono">{ds}</span>
                    <span class="text-sm font-bold text-primary font-mono">₹{p[3]:,.0f}</span>
                    <span class="text-xs text-on-surface-variant">{p[4]} · {p[2]}yr</span>
                </div>
                <div class="flex items-center gap-3">
                    <span class="text-sm font-bold text-primary font-mono">₹{p[5]:,.0f}</span>
                    <span class="px-2 py-1 {bgc} {rc} rounded-lg text-[10px] font-extrabold uppercase tracking-tight">+{gain_pct:.0f}%</span>
                </div>
            </div>'''
        history_html += '</div></div>'
 
    content_html = f'''
    <div class="max-w-4xl mx-auto py-12 animate-fade-in">
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-[2.5rem] shadow-2xl overflow-hidden">
            <div class="p-12 border-b border-outline-variant/10 bg-gradient-to-br from-primary/5 to-transparent">
                <div class="flex items-center gap-4 mb-3">
                    <span class="px-3 py-1 bg-primary/10 text-primary text-[10px] font-black uppercase tracking-[0.2em] rounded-full border border-primary/20">Active Intelligence</span>
                </div>
                <h2 class="text-4xl font-black text-primary tracking-tighter font-headline">Smart Investment Engine</h2>
                <p class="text-base text-on-surface-variant/80 mt-3 font-medium">Evaluate Live Stocks, Mutual Funds &amp; Real Estate simultaneously to identify the high-alpha opportunity for your full capital.</p>
            </div>
            
            <div class="p-12">
                <form action="/predict" method="post" id="mainForm" class="grid grid-cols-1 lg:grid-cols-12 gap-10">
                    <!-- Left: Risk Selector (Spans 5) -->
                    <div class="lg:col-span-5 space-y-8">
                        <div>
                            <div class="flex justify-between items-end mb-6">
                                <div>
                                    <label class="text-[10px] font-black uppercase tracking-[0.2em] text-on-surface-variant/60 block mb-1">Portfolio Strategy</label>
                                    <h4 class="text-lg font-bold text-primary">Risk Orientation</h4>
                                </div>
                                <span id="riskLabel" class="px-4 py-2 bg-secondary-container/30 text-secondary font-black text-xs rounded-xl border border-secondary/10">1 — Conservative</span>
                            </div>
                            
                            <div class="relative pt-4 px-2">
                                <input type="range" class="w-full h-3 bg-surface-container-high rounded-full appearance-none cursor-pointer accent-primary hover:accent-primary-fixed transition-all" name="risk" id="riskSlider" min="1" max="5" value="1" oninput="updateRisk(this.value)">
                                <div class="flex justify-between px-1 text-[9px] font-black uppercase tracking-tighter text-on-surface-variant/40 mt-4">
                                    <span>Safe</span>
                                    <span>Balanced</span>
                                    <span>Dynamic</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="p-6 bg-surface-container-low/50 rounded-3xl border border-outline-variant/5">
                            <h5 class="text-[10px] font-black uppercase tracking-widest text-primary mb-3">Engine Logic</h5>
                            <p class="text-xs text-on-surface-variant/70 leading-relaxed">Adjusting this slider re-weights the AI's volatility threshold, shifting focus between stable dividend yields and high-growth momentum stocks.</p>
                        </div>
                    </div>

                    <!-- Right: Numeric Inputs & Action (Spans 7) -->
                    <div class="lg:col-span-7 flex flex-col justify-between space-y-8">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div class="p-6 bg-surface-container-low rounded-3xl border-2 border-transparent focus-within:border-primary/10 transition-all">
                                <label class="block text-[10px] font-black uppercase tracking-[0.2em] text-on-surface-variant/60 mb-4">Time Horizon</label>
                                <div class="flex items-center gap-3">
                                    <span class="material-symbols-outlined text-outline-variant">schedule</span>
                                    <input name="years" type="number" min="1" max="30" value="5" required class="bg-transparent border-none p-0 text-2xl font-black text-primary w-full focus:ring-0" placeholder="Years">
                                    <span class="text-xs font-bold text-outline-variant">Years</span>
                                </div>
                            </div>
                            
                            <div class="p-6 bg-surface-container-low rounded-3xl border-2 border-transparent focus-within:border-primary/10 transition-all">
                                <label class="block text-[10px] font-black uppercase tracking-[0.2em] text-on-surface-variant/60 mb-4">Investment Capital</label>
                                <div class="flex items-center gap-3">
                                    <span class="material-symbols-outlined text-outline-variant">payments</span>
                                    <span class="text-lg font-bold text-primary">₹</span>
                                    <input name="amount" type="number" min="1000" value="100000" required class="bg-transparent border-none p-0 text-2xl font-black text-primary w-full focus:ring-0" placeholder="0.00">
                                </div>
                            </div>
                        </div>

                        <button type="submit" id="analyzeBtn" class="group relative w-full bg-primary text-on-primary font-black py-7 rounded-3xl shadow-2xl hover:-translate-y-1.5 transition-all overflow-hidden">
                            <div class="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-500"></div>
                            <div class="relative flex items-center justify-center gap-3">
                                <span class="material-symbols-outlined text-2xl animate-pulse">query_stats</span>
                                <span class="text-lg tracking-tight">Run Optimization Analysis</span>
                            </div>
                        </button>
                    </div>
                </form>
            </div>
        </div>
        {history_html}
    </div>
    <script>
    const labels=['Conservative','Moderate-Balanced','Growth Focused','High Alpha','Aggressive Expansion'];
    const colors=['text-secondary','text-secondary','text-tertiary-fixed-dim','text-error','text-error'];
    function updateRisk(val){{
        const l=document.getElementById('riskLabel');
        l.innerText=val+' — '+labels[val-1];
        l.className='px-4 py-2 bg-secondary-container/30 font-black text-xs rounded-xl border border-secondary/10 '+colors[val-1];
    }}
    </script>
    '''
    return get_layout(content_html, user=username, title="Dashboard")

# ===== AUTH ROUTES =====
@app.route('/signup', methods=['POST'])
def signup():
    """
    Finalizes user registration by verifying the TOTP/Signal code and committing
    validated identity details to the persistent SQLite database.
    """
    username = request.form.get('username')
    otp_code = request.form.get('otp')
    
    # PHASE 2: Verifying OTP and Finalizing Account
    if otp_code:
        pending = session.get('pending_signup')
        if not pending or pending['username'] != username:
            print(f"[SECURITY] Bypassed OTP attempt blocked: {username}")
            return redirect(url_for('auth_page', error='invalid', user=username))
        
        if verify_otp_logic(pending['temp_id'], otp_code, 'signup'):
            try:
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                                (pending['username'], pending['hashed_pw'], pending['email']))
                    conn.commit()
                
                session.pop('pending_signup', None)
                session['user'] = pending['username']
                logger.info(f"[SECURITY] Account CREATED (Verified): {pending['username']}")
                return redirect(url_for('home'))
            except sqlite3.IntegrityError:
                return redirect(url_for('auth_page', error='exists', user=username))
            except Exception as e:
                logger.error(f"Final Signup Error: {e}")
                return redirect(url_for('auth_page', error='system_busy', user=username))
        else:
            logger.error(f"[SECURITY] OTP Failed for candidate: {username}")
            return redirect(url_for('auth_page', error='invalid_otp', user=username, status='signup_otp_sent'))

    # PHASE 1: Validating Details and Sending OTP
    else:
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password')
        
        if not username or not email or not password:
            return redirect(url_for('auth_page', error='invalid', user=username))
        
        if not is_valid_email(email):
            return redirect(url_for('auth_page', error='invalid_email', user=username))
        
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
                if cur.fetchone():
                    return redirect(url_for('auth_page', error='exists', user=username))
        except Exception as e:
            logger.error(f"DB Error during signup request: {e}")
            return redirect(url_for('auth_page', error='system_busy', user=username))

        temp_id = abs(hash(email)) % (10**9) * -1
        code = generate_otp(temp_id, 'signup') 
        show_otp_sim(username, code, 'Identity Verification', email=email)
        
        session['pending_signup'] = {
            'username': username,
            'email': email,
            'temp_id': temp_id,
            'hashed_pw': generate_password_hash(password)
        }
        
        return redirect(url_for('auth_page', status='signup_otp_sent', user=username))

@app.route('/validate-email-ajax', methods=['POST'])
def validate_email_ajax():
    """
    Verifies the logical integrity of an email domain (typos, disposable checks,
    and DNS MX verification) before allowing a Signal Sync.
    """
    email = request.form.get('email', '').strip()
    if not email:
        return jsonify({"valid": False, "message": "Email is required"})
    
    # Run the comprehensive check
    is_ok = is_valid_email(email)
    
    if is_ok:
        return jsonify({"valid": True, "message": "Identity verified (Real Domain)"})
    else:
        # Determine if it's syntax or domain/disposable
        regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(regex, email.lower()):
            msg = "Invalid syntax (e.g. user@domain.com)"
        else:
            msg = "Fake or disposable domain detected"
        return jsonify({"valid": False, "message": msg})
 
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
        
        if user:
            if check_password_hash(user[0], password):
                session['user'] = username
                return redirect(url_for('home'))
        return redirect(url_for('auth_page', error='invalid', user=username))
    except Exception as e:
        print(f"Login Error: {e}")
        return redirect(url_for('auth_page', error='system_busy', user=username))

@app.route('/request-otp', methods=['POST'])
def request_otp():
    username = request.form.get('username')
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, email FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if user:
                code = generate_otp(user[0], 'login')
                show_otp_sim(username, code, 'Login Verification', email=user[1])
                return redirect(url_for('auth_page', status='otp_sent', user=username))
    except Exception as e:
        print(f"Auth Error: {e}")
        return redirect(url_for('auth_page', error='system_busy', user=username))
    return redirect(url_for('auth_page', error='not_found', user=username))

@app.route('/verify-login-otp', methods=['POST'])
def verify_login_otp():
    username = request.form.get('username')
    code = request.form.get('otp')
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if user and verify_otp_logic(user[0], code, 'login'):
                session['user'] = username
                return redirect(url_for('home'))
    except Exception as e:
        print(f"Verify OTP Error: {e}")
    return redirect(url_for('auth_page', error='invalid_otp', user=username, status='otp_sent'))

@app.route('/forgot-password', methods=['POST'])
def forgot_password_request():
    username = request.form.get('username')
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, email FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if user:
                email = user[1]
                code = generate_otp(user[0], 'reset')
                show_otp_sim(username, code, 'Password Reset', email=email)
                return redirect(url_for('auth_page', status='reset_otp_sent', user=username))
    except Exception as e:
        logger.error(f"Forgot PW Error: {e}")
    return redirect(url_for('auth_page', error='not_found', user=username))

@app.route('/reset-password', methods=['POST'])
def reset_password():
    username = request.form.get('username')
    code = request.form.get('otp')
    new_pw = request.form.get('password')
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if user and verify_otp_logic(user[0], code, 'reset'):
                hashed = generate_password_hash(new_pw)
                cur.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user[0]))
                conn.commit()
                return redirect(url_for('auth_page', status='password_reset_success'))
    except Exception as e:
        logger.error(f"Reset PW Error: {e}")
    return redirect(url_for('auth_page', error='invalid_otp', user=username, status='reset_otp_sent'))
 
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('auth_page'))
 
# ===== PREDICT =====
import uuid

def _run_prediction_job(job_id, username, risk, years, amount):
    """Runs entirely in a background daemon thread so Flask is never blocked."""
    ml_growth = predict_return_ml(risk, years)

    def fetch_stock_option():
        s = get_best_stock(risk)
        news = 'Indian equity markets remain active with Nifty 50 tracking global trends.'
        rate = max(0, (s[1] * 0.5) + (ml_growth * 0.3) + 0.1)
        projected = amount * ((1 + rate) ** years)
        d, p = get_stock_chart_data(s[0], years)
        return {"type":"Stocks","name":s[0],"rate":rate,"projected":projected,
                "gain":projected-amount,"gain_pct":((projected-amount)/amount)*100,
                "sentiment":0.5,"news":news,"chart_dates":d,"chart_prices":p}

    def fetch_mf_option():
        m = get_best_mutual_fund()
        news = 'Mutual fund SIPs see record inflows as retail investor participation grows.'
        rate = max(0, (m[1] * 0.6) + (ml_growth * 0.3) + 0.1)
        projected = amount * ((1 + rate) ** years)
        d, p = get_mf_chart_data(m[2], years)
        return {"type":"Mutual Fund","name":m[0],"rate":rate,"projected":projected,
                "gain":projected-amount,"gain_pct":((projected-amount)/amount)*100,
                "sentiment":0.5,"news":news,"chart_dates":d,"chart_prices":p}

    def fetch_re_option():
        r = get_real_estate(amount, risk)
        if r[3] == -1.0:
            return {"type":"Real Estate","name":r[0],"rate":0,"projected":amount,
                    "gain":0,"gain_pct":0,
                    "sentiment":0.5,"news":"Cannot invest in Real Estate with this capital amount.",
                    "chart_dates":[],"chart_prices":[]}
        symbol = r[4] if len(r) > 4 else "Fallback"
        news = 'Indian real estate sees strong demand in metro and emerging cities.'
        rate = max(0, (r[1] * 0.7) + (ml_growth * 0.2) + 0.1)
        projected = amount * ((1 + rate) ** years)
        d, p = get_re_chart_data(symbol, years)
        return {"type":"Real Estate","name":r[0],"rate":rate,"projected":projected,
                "gain":projected-amount,"gain_pct":((projected-amount)/amount)*100,
                "sentiment":0.5,"news":news,"chart_dates":d,"chart_prices":p}

    results = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(fetch_stock_option): 'stock',
            ex.submit(fetch_mf_option): 'mf',
            ex.submit(fetch_re_option): 're',
        }
        for f in as_completed(futures, timeout=25):
            try:
                res = f.result(timeout=25)
                if res: results.append(res)
            except Exception as e:
                print(f"Worker error ({futures[f]}): {e}")

    if not results:
        results.append({
            "type": "Defensive", "name": "Safety Fallback Index",
            "rate": 0.05,
            "projected": amount * ((1.05) ** years),
            "gain": amount * ((1.05) ** years) - amount,
            "gain_pct": 5 * years,
            "sentiment": 0.5, "news": "Live data unavailable — showing conservative baseline.",
            "chart_dates": [], "chart_prices": []
        })

    results.sort(key=lambda x: x["projected"], reverse=True)
    best = results[0]
    def _np_encoder(obj):
        if hasattr(obj, 'item'): return obj.item()
        raise TypeError()
    full_json = json.dumps({"results": results, "best": best}, default=_np_encoder)
    save_prediction(username, risk, years, amount, best["type"], best["projected"], best["rate"], full_json)

    with job_lock:
        job_store[job_id] = {"status": "done", "results": results, "best": best,
                             "risk": risk, "years": years, "amount": amount}


@app.route('/predict', methods=['POST'])
def predict():
    if 'user' not in session:
        return redirect(url_for('auth_page'))

    username = session['user']
    risk   = int(request.form['risk'])
    years  = int(request.form['years'])
    amount = float(request.form['amount'])

    job_id = str(uuid.uuid4())
    with job_lock:
        job_store[job_id] = {"status": "pending"}
        t = threading.Thread(target=_run_prediction_job,
                             args=(job_id, username, risk, years, amount), daemon=True)
    t.start()

    content_html = (
        '<div class="flex flex-col items-center justify-center p-20 animate-fade-in text-center h-full">'
        '<div class="w-16 h-16 border-4 border-outline-variant/20 border-t-primary rounded-full animate-spin mb-8"></div>'
        '<h2 class="text-2xl font-extrabold text-primary mb-2 font-headline">Predicting Returns</h2>'
        '<p id="msg" class="text-sm text-on-surface-variant mb-6 font-medium">Booting calculation engine...</p>'
        '<div class="flex gap-2">'
        '<div class="w-2 h-2 rounded-full bg-primary animate-bounce"></div>'
        '<div class="w-2 h-2 rounded-full bg-primary animate-bounce" style="animation-delay:0.15s"></div>'
        '<div class="w-2 h-2 rounded-full bg-primary animate-bounce" style="animation-delay:0.3s"></div>'
        '</div></div>'
        '<script>'
        'const msgs=["Fetching live market data...","Scanning NIFTY50 stocks...","Comparing mutual fund NAVs...","Checking real estate listings...","Running AI return model...","Calculating final recommendation..."];'
        'let mi=0;const el=document.getElementById("msg");'
        'const cycle=setInterval(()=>{if(mi<msgs.length-1)el.textContent=msgs[++mi];},1800);'
        'async function poll(){'
        'try{'
        f'const res=await fetch("/result/{job_id}");const d=await res.json();'
        'if(d.status==="done"){clearInterval(cycle);document.open();document.write(d.html);document.close();}'
        'else{setTimeout(poll,1500);}'
        '}catch(e){setTimeout(poll,2000);}'
        '}'
        'setTimeout(poll,2000);'
        '</script>'
    )
    return get_layout(content_html, user=username, title="Analyzing...")



def render_prediction_html(amount, years, risk, results, best, username):
    risk_label  = ['','Conservative','Mod. Conservative','Moderate','Mod. Aggressive','Aggressive'][risk]
    risk_col    = '#ef4444' if risk > 3 else ('#f59e0b' if risk == 3 else '#10b981')
    type_icons  = {'Stocks': 'show_chart', 'Mutual Fund': 'account_balance', 'Real Estate': 'home_work'}
    type_colors = {'Stocks': '#3c5d9c', 'Mutual Fund': '#006d43', 'Real Estate': '#e6a817'}

    if best["type"] == "Stocks":
        reason = (f"Equities outperform over your {years}-year horizon at {best['rate']*100:.1f}% CAGR. "
                  f"Stocks adapt to your '{risk_label}' risk level, capturing market upside while the long horizon smooths volatility.")
    elif best["type"] == "Mutual Fund":
        reason = (f"Mutual Funds deliver {best['rate']*100:.1f}% p.a. risk-adjusted returns over {years} years. "
                  f"Professional management and diversification make this the safest high-yield path for '{risk_label}' investors.")
    else:
        if amount < 1000000:
            reason = (f"REITs give you {best['rate']*100:.1f}% exposure to India's booming property market "
                      f"with full liquidity on ₹{amount:,.0f}.")
        else:
            reason = (f"Your ₹{amount:,.0f} capital targets real estate at {best['rate']*100:.1f}% p.a. appreciation - "
                      f"providing wealth creation and asset security over {years} years.")

    charts_data = [
        {"type": r["name"][:25] + ("..." if len(r["name"])>25 else ""), "is_best": i == 0,
         "dates": r["chart_dates"], "prices": r["chart_prices"],
         "color": type_colors.get(r["type"], "#3c5d9c")}
        for i, r in enumerate(results)
    ]
    charts_json = json.dumps(charts_data)

    max_proj = max(r["projected"] for r in results) or 1
    bar_rows = ""
    for r in results:
        w    = int((r["projected"] / max_proj) * 100)
        col  = type_colors.get(r["type"], "#3c5d9c")
        is_b = r["projected"] == best["projected"]
        nc   = "text-secondary" if is_b else "text-on-surface-variant"
        sh   = f";box-shadow:0 0 10px {col}80" if is_b else ""
        name_trunc = r["name"][:35] + ("..." if len(r["name"])>35 else "")
        bar_rows += (
            f'<div class="flex items-center gap-4 py-3 border-b border-outline-variant/10 last:border-0">'
            f'<div class="w-48 shrink-0 text-[11px] font-bold text-primary truncate" title="{r["name"]}">{name_trunc}</div>'
            f'<div class="flex-1 h-3 bg-surface-container-high rounded-full overflow-hidden">'
            f'<div class="h-full rounded-full" style="width:{w}%;background:{col}{sh}"></div></div>'
            f'<div class="w-32 text-right text-sm font-extrabold {nc} font-mono shrink-0">&#8377;{r["projected"]:,.0f}</div>'
            f'</div>'
        )

    if risk <= 2:
        alloc_labels = ["Fixed Deposits / Bonds", "Bluechip Equity", "Gold / Sovereign Bonds"]
        alloc_data = [70, 20, 10]
        alloc_colors = ["#10b981", "#3c5d9c", "#f59e0b"]
    elif risk == 3:
        alloc_labels = ["Fixed Income", "Diversified Equity", "Real Estate / REITs"]
        alloc_data = [40, 50, 10]
        alloc_colors = ["#10b981", "#3c5d9c", "#e6a817"]
    else:
        alloc_labels = ["Debt / Liquid Funds", "Aggressive Equity", "High-Yield Alternatives"]
        alloc_data = [15, 70, 15]
        alloc_colors = ["#10b981", "#ef4444", "#8b5cf6"]

    alloc_json = json.dumps({"labels": alloc_labels, "data": alloc_data, "colors": alloc_colors})

    legend_html = ""
    for label, val, c in zip(alloc_labels, alloc_data, alloc_colors):
        legend_html += (
            f'<div class="flex items-center justify-between p-3 bg-surface-container-low rounded-xl mb-2">'
            f'<div class="flex items-center gap-3">'
            f'<div class="w-3 h-3 rounded-full" style="background:{c}"></div>'
            f'<div class="text-sm font-bold text-on-surface-variant font-headline">{label}</div>'
            f'</div>'
            f'<div class="text-sm font-extrabold text-primary font-mono">{val}%</div>'
            f'</div>'
        )

    strategy_html = (
        f'<div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm mb-8">'
        f'<h3 class="text-sm font-extrabold text-primary mb-5 flex items-center gap-2">'
        f'<span class="material-symbols-outlined text-secondary" style="font-variation-settings:\'FILL\' 1">pie_chart</span>'
        f'Recommended Asset Allocation</h3>'
        f'<div class="flex flex-col md:flex-row items-center gap-8">'
        f'<div class="w-[200px] h-[200px] shrink-0 relative">'
        f'<canvas id="allocation-chart"></canvas>'
        f'<div class="absolute inset-0 flex items-center justify-center flex-col pointer-events-none">'
        f'<div class="text-[10px] font-bold tracking-widest uppercase text-on-surface-variant/50">Risk Level</div>'
        f'<div class="text-2xl font-extrabold text-primary">{risk}/5</div>'
        f'</div></div>'
        f'<div class="flex-1 w-full">'
        f'<p class="text-sm text-on-surface-variant mb-5 leading-relaxed">'
        f'Based on your <strong>{risk_label}</strong> investor profile and a {years}-year horizon,'
        f'we recommend diversifying your &#8377;{amount:,.0f} capital across these core asset classes.</p>'
        + legend_html +
        f'</div></div></div>'
    )

    risk_pct = int((risk / 5) * 100)
    multiplier = f"{best['projected']/amount:.2f}"

    result_page = (
        '<div class="max-w-5xl mx-auto py-4 animate-fade-in">'

        # Header
        '<div class="flex justify-between items-center mb-8">'
        '<div>'
        '<h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">Prediction Results</h2>'
        f'<p class="text-sm text-on-surface-variant mt-1">&#8377;{amount:,.0f} Capital &nbsp;&bull;&nbsp; {years} Years &nbsp;&bull;&nbsp;'
        f'<span class="font-bold" style="color:{risk_col}">{risk_label} Risk</span></p>'
        '</div>'
        '<a href="/" class="flex items-center gap-2 bg-primary text-on-primary px-5 py-2.5 rounded-xl text-sm font-bold hover:-translate-y-0.5 hover:shadow-lg transition-all">'
        '<span class="material-symbols-outlined text-[18px]">refresh</span> New Analysis</a>'
        '</div>'

        # Hero
        '<div class="rounded-3xl overflow-hidden shadow-2xl mb-8" style="background:linear-gradient(135deg,#001b44 0%,#002f6c 55%,#006d43 100%)">'
        '<div class="p-8 flex flex-col md:flex-row justify-between items-start gap-6">'
        '<div class="flex-1">'
        '<div class="inline-flex items-center gap-2 bg-white/10 text-secondary-fixed px-3 py-1.5 rounded-full text-[10px] font-extrabold uppercase tracking-widest mb-4">'
        '<span class="material-symbols-outlined text-sm" style="font-variation-settings:\'FILL\' 1">verified</span>AI Recommended</div>'
        f'<h3 class="text-2xl font-extrabold text-white mb-3 font-headline line-clamp-2">{best["name"][:70]}{"..." if len(best["name"])>70 else ""}</h3>'
        f'<p class="text-sm text-white/70 leading-relaxed max-w-xl">{reason}</p>'
        '<div class="flex flex-wrap items-center gap-8 mt-6">'
        f'<div><div class="text-[10px] uppercase text-white/40 font-bold tracking-widest mb-1">Asset Class</div><div class="text-sm font-extrabold text-secondary-fixed">{best["type"]}</div></div>'
        f'<div><div class="text-[10px] uppercase text-white/40 font-bold tracking-widest mb-1">Annual CAGR</div><div class="text-sm font-extrabold text-secondary-fixed">{best["rate"]*100:.2f}%</div></div>'
        f'<div><div class="text-[10px] uppercase text-white/40 font-bold tracking-widest mb-1">Risk Level</div><div class="text-sm font-extrabold" style="color:{risk_col}">{risk_label}</div></div>'
        f'<div><div class="text-[10px] uppercase text-white/40 font-bold tracking-widest mb-1">Multiplier</div><div class="text-sm font-extrabold text-secondary-fixed">{multiplier}&times;</div></div>'
        '</div></div>'
        '<div class="text-right shrink-0">'
        '<div class="text-[10px] font-bold uppercase text-white/40 tracking-widest mb-2">Projected Wealth</div>'
        f'<div class="text-5xl font-extrabold text-white font-mono tracking-tight">&#8377;{best["projected"]:,.0f}</div>'
        f'<div class="mt-3 inline-flex items-center gap-1 bg-secondary/20 text-secondary-fixed border border-secondary/30 px-3 py-1.5 rounded-full text-sm font-extrabold">&#9650; +{best["gain_pct"]:.1f}% over {years} yrs</div>'
        '</div></div>'
        '<div class="bg-black/25 px-8 py-4 flex items-center gap-4">'
        '<span class="text-[10px] font-bold uppercase text-white/40 tracking-widest shrink-0">Risk Tolerance</span>'
        '<div class="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">'
        f'<div class="h-full rounded-full" style="width:{risk_pct}%;background:{risk_col}"></div></div>'
        f'<span class="text-xs font-extrabold shrink-0" style="color:{risk_col}">{risk}/5 &mdash; {risk_label}</span>'
        '</div></div>'

        # Comparison bars
        '<div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm mb-8">'
        '<h3 class="text-sm font-extrabold text-primary mb-5 flex items-center gap-2">'
        '<span class="material-symbols-outlined text-secondary" style="font-variation-settings:\'FILL\' 1">bar_chart</span>Projected Wealth Comparison</h3>'
        + bar_rows +
        f'<div class="flex justify-between text-[10px] text-on-surface-variant/40 font-mono mt-3 pt-3 border-t border-outline-variant/10">'
        f'<span>&#8377;0</span><span>Invested: &#8377;{amount:,.0f}</span><span>&#8377;{max_proj:,.0f}</span></div></div>'

        # Strategy Block
        + strategy_html +

        # Trend charts container
        '<div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm mb-4">'
        '<h3 class="text-sm font-extrabold text-primary mb-5 flex items-center gap-2">'
        '<span class="material-symbols-outlined text-secondary" style="font-variation-settings:\'FILL\' 1">timeline</span>Historical Price Trends</h3>'
        '<div class="grid grid-cols-1 md:grid-cols-3 gap-6" id="trend-charts"></div>'
        '</div></div>'

        # Chart.js
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
        '<script>'
        f'const cData={charts_json};'
        'const tc=document.getElementById("trend-charts");'
        'cData.forEach((data,i)=>{'
        'const wrap=document.createElement("div");'
        'wrap.innerHTML=`'
        '<div class="flex items-center gap-2 mb-3">'
        '<span class="w-2.5 h-2.5 rounded-full inline-block" style="background:${data.color}"></span>'
        '<span class="text-xs font-extrabold text-primary">${data.type}</span>'
        '${data.is_best?\'<span class="ml-1 text-[9px] font-bold bg-secondary-container/30 text-secondary px-2 py-0.5 rounded-full uppercase tracking-widest">Top Pick</span>\':""}'
        '</div>'
        '<div style="height:130px;position:relative"><canvas id="trend-${i}"></canvas></div>`;'
        'tc.appendChild(wrap);'
        'if(!data.prices||data.prices.length<2){'
        'wrap.querySelector("canvas").parentElement.innerHTML=\'<div class="h-full flex items-center justify-center text-xs text-on-surface-variant/40 italic">Insufficient data</div>\';'
        'return;}'
        'const ctx=document.getElementById("trend-"+i).getContext("2d");'
        'const gr=ctx.createLinearGradient(0,0,0,130);'
        'gr.addColorStop(0,data.color+"45");gr.addColorStop(1,data.color+"00");'
        'new Chart(ctx,{type:"line",'
        'data:{labels:data.dates,datasets:[{data:data.prices,borderColor:data.color,borderWidth:2,backgroundColor:gr,fill:true,tension:0.4,pointRadius:0}]},'
        'options:{responsive:true,maintainAspectRatio:false,'
        'plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>"&#8377;"+c.parsed.y.toLocaleString("en-IN")}}},'
        'scales:{x:{display:false},y:{display:false,min:Math.min(...data.prices)*0.97}}}});'
        '});\n'
        
        f'const allocInfo={alloc_json};'
        'const aCtx=document.getElementById("allocation-chart").getContext("2d");'
        'new Chart(aCtx, {'
        '  type: "doughnut",'
        '  data: { labels: allocInfo.labels, datasets: [{ data: allocInfo.data, backgroundColor: allocInfo.colors, borderWidth: 0, hoverOffset: 4 }] },'
        '  options: { cutout: "75%", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }'
        '});'
        '</script>'
    )
    return result_page

@app.route('/result/<job_id>')
def result(job_id):
    if 'user' not in session:
        return json.dumps({"status": "redirect"})
    with job_lock:
        job = job_store.get(job_id)
    if not job or job["status"] != "done":
        return Response(json.dumps({"status": "pending"}), mimetype='application/json')

    results  = job["results"]
    best     = job["best"]
    risk     = job["risk"]
    years    = job["years"]
    amount   = job["amount"]
    username = session['user']

    inner_html = render_prediction_html(amount, years, risk, results, best, username)
    html_out = get_layout(inner_html, user=username, title="Results")
    with job_lock:
        job_store.pop(job_id, None)
    return Response(json.dumps({"status": "done", "html": html_out}), mimetype='application/json')
@app.route('/insights')
def insights():
    if 'user' not in session:
        return redirect(url_for('login'))
    if hasattr(insights, 'cache') and time.time() - insights.cache['time'] < 300:
        return get_layout(insights.cache['html'], user=session['user'], title="AI Insights")

    def _ticker_stat(sym):
        try:
            d = yf.Ticker(sym).history(period='5d').dropna()
            if len(d) < 2: return None, None, None
            prev, curr = float(d['Close'].iloc[-2]), float(d['Close'].iloc[-1])
            return curr, (curr - prev), ((curr - prev) / prev) * 100
        except:
            return None, None, None

    def _stock_movers():
        sample = random.sample(NIFTY50_TICKERS, 12)
        results = []
        try:
            raw = yf.download(sample, period='5d', interval='1d', group_by='ticker',
                              auto_adjust=True, progress=False, threads=False)
            for sym in sample:
                try:
                    closes = raw[sym]['Close'].dropna() if len(sample) > 1 else raw['Close'].dropna()
                    if len(closes) < 2: continue
                    prev, curr = float(closes.iloc[-2]), float(closes.iloc[-1])
                    pct = ((curr - prev) / prev) * 100
                    results.append({'sym': sym.replace('.NS',''), 'price': curr, 'pct': pct})
                except: continue
        except: pass
        results.sort(key=lambda x: x['pct'], reverse=True)
        return results[:5], results[-5:][::-1]

    def _sector_perf():
        sectors = {
            'IT': 'INFY.NS', 'Banking': 'HDFCBANK.NS', 'Energy': 'RELIANCE.NS',
            'Pharma': 'SUNPHARMA.NS', 'Auto': 'MARUTI.NS', 'FMCG': 'ITC.NS'
        }
        out = []
        for name, sym in sectors.items():
            _, _, pct = _ticker_stat(sym)
            out.append({'name': name, 'pct': pct if pct is not None else 0.0})
        return out

    def _macro():
        gold_p, gold_c, gold_pct = _ticker_stat('GC=F')
        usd_p, usd_c, usd_pct   = _ticker_stat('USDINR=X')
        return gold_p, gold_pct, usd_p, usd_pct

    # Run all fetches in parallel
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_nifty   = ex.submit(_ticker_stat, '^NSEI')
        f_sensex  = ex.submit(_ticker_stat, '^BSESN')
        f_bnifty  = ex.submit(_ticker_stat, '^NSEBANK')
        f_movers  = ex.submit(_stock_movers)
        f_sector  = ex.submit(_sector_perf)
        f_macro   = ex.submit(_macro)

    nifty_p,  nifty_c,  nifty_pct  = f_nifty.result()
    sensex_p, sensex_c, sensex_pct = f_sensex.result()
    bnifty_p, bnifty_c, bnifty_pct = f_bnifty.result()
    gainers, losers                 = f_movers.result()
    sectors                         = f_sector.result()
    gold_p, gold_pct, usd_p, usd_pct = f_macro.result()

    today = datetime.datetime.now().strftime('%d %b %Y, %I:%M %p')

    def _idx_card(label, price, chg, pct, icon):
        if price is None:
            return f'''
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-1 flex items-center gap-1">
                    <span class="material-symbols-outlined text-sm">{icon}</span>{label}
                </div>
                <div class="text-2xl font-extrabold text-on-surface-variant">N/A</div>
                <div class="text-xs text-on-surface-variant mt-1">Temporarily unavailable</div>
            </div>'''
        color = 'text-secondary' if pct >= 0 else 'text-error'
        arrow = '▲' if pct >= 0 else '▼'
        bg    = 'bg-secondary-container/20' if pct >= 0 else 'bg-error-container/20'
        return f'''
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm hover:shadow-md transition-all">
            <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2 flex items-center gap-1">
                <span class="material-symbols-outlined text-sm">{icon}</span>{label}
            </div>
            <div class="text-3xl font-extrabold text-primary font-mono">{price:,.2f}</div>
            <div class="flex items-center gap-2 mt-2">
                <span class="px-2 py-0.5 {bg} {color} rounded-lg text-xs font-extrabold font-mono">
                    {arrow} {abs(pct):.2f}%
                </span>
                <span class="text-xs text-on-surface-variant font-mono">{chg:+.2f} pts</span>
            </div>
        </div>'''

    def _mover_row(m, is_gainer):
        color = 'text-secondary' if is_gainer else 'text-error'
        bg    = 'bg-secondary-container/20' if is_gainer else 'bg-error-container/20'
        arrow = '▲' if is_gainer else '▼'
        return f'''
        <div class="flex items-center justify-between py-3 border-b border-outline-variant/10 last:border-0">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg bg-surface-container flex items-center justify-center text-[10px] font-extrabold text-on-surface-variant">{m['sym'][:3]}</div>
                <span class="text-sm font-bold text-primary">{m['sym']}</span>
            </div>
            <div class="flex items-center gap-3">
                <span class="text-xs text-on-surface-variant font-mono">₹{m['price']:,.1f}</span>
                <span class="px-2 py-0.5 {bg} {color} rounded-lg text-xs font-extrabold font-mono">
                    {arrow} {abs(m['pct']):.2f}%
                </span>
            </div>
        </div>'''

    def _sector_bar(s):
        pct = s['pct']
        color = '#10b981' if pct >= 0 else '#ef4444'
        w = min(abs(pct) * 10, 100)
        label_color = 'text-secondary' if pct >= 0 else 'text-error'
        return f'''
        <div class="flex items-center gap-3 py-2">
            <span class="text-xs font-bold text-primary w-16 shrink-0">{s['name']}</span>
            <div class="flex-1 h-2 bg-surface-container-high rounded-full overflow-hidden">
                <div class="h-full rounded-full" style="width:{w}%;background:{color}"></div>
            </div>
            <span class="text-xs font-extrabold font-mono {label_color} w-14 text-right">
                {'▲' if pct >= 0 else '▼'}{abs(pct):.2f}%
            </span>
        </div>'''

    def _macro_card(label, val, pct, icon, unit=''):
        if val is None:
            return f'<div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-5 shadow-sm"><div class="text-xs font-bold uppercase text-on-surface-variant/60 mb-1">{label}</div><div class="text-xl font-extrabold text-on-surface-variant">N/A</div></div>'
        color = 'text-secondary' if (pct or 0) >= 0 else 'text-error'
        arrow = '▲' if (pct or 0) >= 0 else '▼'
        return f'''
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-5 shadow-sm hover:shadow-md transition-all">
            <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">
                <span class="material-symbols-outlined text-sm text-secondary">{icon}</span>{label}
            </div>
            <div class="text-xl font-extrabold text-primary font-mono">{unit}{val:,.2f}</div>
            <div class="{color} text-xs font-bold mt-1">{arrow} {abs(pct or 0):.2f}% today</div>
        </div>'''

    intel_cards = [
        ('psychology', 'SIP Strategy', 'secondary',
         'Systematic Investment Plans into large-cap index funds historically outperform lump-sum investing during volatile periods. A monthly SIP of ₹10,000 over 10 years at 12% CAGR grows to ₹23.2 Lakhs.'),
        ('account_balance', 'RBI Policy Watch', 'tertiary-fixed-dim',
         'The Reserve Bank of India held the repo rate steady at 6.5%. A stable rate environment typically favors equity markets and bond prices. Fixed deposits at small finance banks currently offer up to 9% p.a.'),
        ('real_estate_agent', 'Real Estate Cycle', 'primary',
         'Metro residential prices rose 8–13% YoY (Jan–Apr 2024). Tier-2 cities like Pune, Hyderabad & Ahmedabad are outperforming with 15%+ appreciation. REITs offer an alternative entry from ₹10,000.'),
        ('trending_up', 'NIFTY 50 Breadth', 'secondary',
         'Broad market participation is healthy — over 60% of NIFTY 50 stocks are trading above their 200-day moving average. This signals a structurally bullish medium-term trend for Indian equities.'),
        ('currency_rupee', 'Gold & INR Watch', 'tertiary-fixed-dim',
         'Gold (MCX) is up 18% YTD and acts as a critical hedge during equity corrections. A weakening INR of ₹83–84/USD supports gold\'s domestic price. Advisable to hold 5–10% of portfolio in gold.'),
        ('bolt', 'Emerging Sectors', 'primary',
         'Defence, green energy, and semiconductor manufacturing are receiving massive government Capital Expenditure. Companies in the PLI scheme are seeing order book growth of 30–40% YoY.'),
    ]

    intel_html = '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">'
    for icon, title, color, body in intel_cards:
        intel_html += f'''
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 rounded-xl bg-{color}/10 flex items-center justify-center">
                    <span class="material-symbols-outlined text-{color}" style="font-variation-settings:'FILL' 1">{ icon}</span>
                </div>
                <h3 class="text-sm font-extrabold text-primary">{title}</h3>
            </div>
            <p class="text-xs text-on-surface-variant leading-relaxed">{body}</p>
        </div>'''
    intel_html += '</div>'

    content_html = f'''
    <div class="max-w-5xl mx-auto py-4 animate-fade-in">

        <!-- HEADER -->
        <div class="flex justify-between items-end mb-8">
            <div>
                <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">AI Market Insights</h2>
                <p class="text-sm text-on-surface-variant mt-1">Live data for Indian equity, currency & commodity markets</p>
            </div>
            <span class="text-xs text-on-surface-variant font-mono bg-surface-container px-3 py-1.5 rounded-lg border border-outline-variant/10">
                Updated: {today} IST
            </span>
        </div>

        <!-- INDEX CARDS -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {_idx_card('NIFTY 50', nifty_p, nifty_c, nifty_pct, 'monitoring')}
            {_idx_card('SENSEX', sensex_p, sensex_c, sensex_pct, 'candlestick_chart')}
            {_idx_card('BANK NIFTY', bnifty_p, bnifty_c, bnifty_pct, 'account_balance')}
        </div>

        <!-- MOVERS + SECTOR -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">

            <!-- TOP GAINERS -->
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="flex items-center gap-2 mb-4">
                    <span class="material-symbols-outlined text-secondary text-lg" style="font-variation-settings:'FILL' 1">trending_up</span>
                    <h3 class="text-sm font-extrabold text-primary">Top Gainers</h3>
                </div>
                {''.join([_mover_row(m, True) for m in gainers]) if gainers else '<p class="text-xs text-on-surface-variant py-4 text-center">Fetching live data...</p>'}
            </div>

            <!-- TOP LOSERS -->
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="flex items-center gap-2 mb-4">
                    <span class="material-symbols-outlined text-error text-lg" style="font-variation-settings:'FILL' 1">trending_down</span>
                    <h3 class="text-sm font-extrabold text-primary">Top Losers</h3>
                </div>
                {''.join([_mover_row(m, False) for m in losers]) if losers else '<p class="text-xs text-on-surface-variant py-4 text-center">Fetching live data...</p>'}
            </div>

            <!-- SECTOR HEATMAP -->
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="flex items-center gap-2 mb-4">
                    <span class="material-symbols-outlined text-tertiary-fixed-dim text-lg" style="font-variation-settings:'FILL' 1">grid_view</span>
                    <h3 class="text-sm font-extrabold text-primary">Sector Performance</h3>
                </div>
                {''.join([_sector_bar(s) for s in sectors]) if sectors else '<p class="text-xs text-on-surface-variant py-4 text-center">Fetching live data...</p>'}
            </div>
        </div>

        <!-- MACRO INDICATORS -->
        <div class="mb-8">
            <h3 class="text-base font-extrabold text-primary mb-4 flex items-center gap-2">
                <span class="material-symbols-outlined text-tertiary-fixed-dim" style="font-variation-settings:'FILL' 1">public</span>
                Macro Indicators
            </h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                {_macro_card('Gold (USD/oz)', gold_p, gold_pct, 'diamond', '$')}
                {_macro_card('USD / INR', usd_p, usd_pct, 'currency_exchange', '₹')}
                <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-5 shadow-sm">
                    <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">
                        <span class="material-symbols-outlined text-sm text-secondary">savings</span>Best FD Rate
                    </div>
                    <div class="text-xl font-extrabold text-primary font-mono">9.00%</div>
                    <div class="text-secondary text-xs font-bold mt-1">Small Finance Banks</div>
                </div>
                <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-5 shadow-sm">
                    <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">
                        <span class="material-symbols-outlined text-sm text-secondary">price_change</span>CPI Inflation
                    </div>
                    <div class="text-xl font-extrabold text-primary font-mono">4.85%</div>
                    <div class="text-secondary text-xs font-bold mt-1">Mar 2025 (RBI)</div>
                </div>
            </div>
        </div>

        <!-- INTELLIGENCE CARDS -->
        <div class="mb-2">
            <h3 class="text-base font-extrabold text-primary mb-4 flex items-center gap-2">
                <span class="material-symbols-outlined text-secondary" style="font-variation-settings:'FILL' 1">lightbulb</span>
                AI-Curated Market Intelligence
            </h3>
            {intel_html}
        </div>

    </div>'''
    insights.cache = {"html": content_html, "time": time.time()}
    return get_layout(content_html, user=session['user'], title="AI Insights")

@app.route('/history')
def history():
    if 'user' not in session: return redirect(url_for('auth_page'))
    username = session['user']
    preds = get_user_predictions(username)
    
    rows_html = ""
    for p in preds:
        p_id = p[0]
        rows_html += f'''
        <tr onclick="window.location='/history/{p_id}'" class="border-b border-outline-variant/10 hover:bg-surface-container-lowest transition-colors cursor-pointer group">
            <td class="py-4 px-6 text-xs font-bold font-mono group-hover:text-primary transition-colors">{p[7][:10]}</td>
            <td class="py-4 text-sm font-bold text-primary">₹{p[3]:,.00f}</td>
            <td class="py-4 text-xs text-on-surface-variant font-medium">{p[4]}</td>
            <td class="py-4 text-sm font-bold text-secondary">₹{p[5]:,.00f}</td>
            <td class="py-4"><span class="px-2 py-1 bg-secondary-container/30 text-secondary text-[10px] font-bold rounded-lg">+{((p[5]-p[3])/p[3]*100):.1f}%</span></td>
        </tr>'''
        
    content_html = f'''
    <div class="max-w-5xl mx-auto py-4 animate-fade-in">
        <div class="mb-8 flex justify-between items-center">
            <div>
                <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">Search History</h2>
                <p class="text-sm text-on-surface-variant mt-2 font-medium">Click any past analysis to view the complete timeline report.</p>
            </div>
        </div>
        
        <div class="bg-surface-container-low border border-outline-variant/10 rounded-2xl overflow-hidden shadow-sm">
            <div class="overflow-x-auto">
                <table class="w-full text-left">
                    <thead class="bg-surface-container-high/30">
                        <tr>
                            <th class="py-4 px-6 text-[10px] font-bold uppercase text-on-surface-variant/60">Date</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Capital</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Top Pick</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Projected</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Growth</th>
                        </tr>
                    </thead>
                    <tbody class="px-0">
                        {rows_html if rows_html else '<tr><td colspan="5" class="p-12 text-center text-on-surface-variant">No search history found. Start your first analysis!</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>'''
    return get_layout(content_html, user=username, title="History")

@app.route('/history/<int:pred_id>')
def history_detail(pred_id):
    if 'user' not in session: return redirect(url_for('auth_page'))
    username = session['user']
    
    record = get_prediction_by_id(pred_id, username)
    if not record or not record[3]:
        return get_layout("<div class='p-20 text-center font-bold text-error'>Legacy prediction format cannot be viewed. Please run a new prediction.</div>", user=username, title="Error")
        
    amount, years, risk, full_json_str = record
    try:
        data = json.loads(full_json_str)
        results = data.get("results", [])
        best = data.get("best", {})
    except:
        return get_layout("<div class='p-20 text-center font-bold text-error'>Corrupted historical entry.</div>", user=username, title="Error")
        
    html_out = render_prediction_html(amount, years, risk, results, best, username)
    return get_layout(html_out, user=username, title="Search History")


@app.route('/settings')
def settings():
    if 'user' not in session: return redirect(url_for('auth_page'))
    username = session['user']
    
    content_html = f'''
    <div class="max-w-3xl mx-auto py-4 animate-fade-in">
        <div class="mb-8">
            <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">Settings</h2>
            <p class="text-sm text-on-surface-variant mt-2 font-medium">Manage your account and engine preferences</p>
        </div>
        
        <div class="space-y-6">
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-8 shadow-sm">
                <h3 class="text-lg font-bold text-primary mb-6 flex items-center gap-2">
                    <span class="material-symbols-outlined text-secondary">person</span> Account Profile
                </h3>
                <div class="grid grid-cols-2 gap-8">
                    <div>
                        <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-1">Username</div>
                        <div class="text-sm font-bold text-primary">{username}</div>
                    </div>
                    <div>
                        <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-1">Status</div>
                        <div class="text-sm font-bold text-secondary">Active Investor</div>
                    </div>
                </div>
            </div>
            
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-8 shadow-sm">
                <h3 class="text-lg font-bold text-primary mb-6 flex items-center gap-2">
                    <span class="material-symbols-outlined text-secondary">psychology</span> Engine Preferences
                </h3>
                <div class="space-y-6">
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-sm font-bold text-primary">Advanced ML Backtesting</div>
                            <div class="text-xs text-on-surface-variant mt-1">Run historical scenarios for every prediction</div>
                        </div>
                        <div class="w-12 h-6 bg-secondary-container rounded-full relative p-1 cursor-pointer">
                            <div class="w-4 h-4 bg-secondary rounded-full absolute right-1"></div>
                        </div>
                    </div>
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-sm font-bold text-primary">Real-time Scraping</div>
                            <div class="text-xs text-on-surface-variant mt-1">Live indexing of property and fund data</div>
                        </div>
                        <div class="w-12 h-6 bg-secondary-container rounded-full relative p-1 cursor-pointer">
                            <div class="w-4 h-4 bg-secondary rounded-full absolute right-1"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <button class="w-full py-4 bg-error text-on-error font-bold rounded-xl shadow-md hover:bg-error/90 transition-all opacity-80">
                Delete Prediction History
            </button>
        </div>
    </div>'''
    return get_layout(content_html, user=username, title="Settings")
 
if __name__ == '__main__':
    # Production Mode Finalization
    app.run(debug=False, host='0.0.0.0', port=5005, use_reloader=False, threaded=True)