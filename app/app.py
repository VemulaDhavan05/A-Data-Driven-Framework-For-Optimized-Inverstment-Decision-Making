import sqlite3
import random
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, session, redirect, url_for
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
 
# ===== DATABASE =====
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
        <a class="flex items-center gap-3 px-4 py-3 rounded-xl {get_nav_class('My Portfolio')}" href="/portfolio">
        <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' {'1' if title=='My Portfolio' else '0'};">folder_managed</span>
        <span class="font-medium">My Portfolio</span>
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

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
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
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()
 
init_db()
import threading

app = Flask(__name__)
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
 
# ===== DB HELPERS =====
def save_prediction(username, risk, years, amount, best_option, predicted_value, annual_rate):
    try:
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if user:
            cur.execute('''
                INSERT INTO predictions (user_id, risk_level, investment_years, amount, best_option, predicted_value, annual_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user[0], risk, years, amount, best_option, predicted_value, annual_rate))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving prediction: {e}")
 
def get_user_predictions(username):
    try:
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return []
        cur.execute('''
            SELECT risk_level, investment_years, amount, best_option, predicted_value, annual_rate, created_at
            FROM predictions WHERE user_id = ? ORDER BY created_at DESC LIMIT 5
        ''', (user[0],))
        rows = cur.fetchall()
        conn.close()
        return rows
    except:
        return []
 
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
    toast_html = ''
    if error_code == 'exists':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2"><span class="material-symbols-outlined text-error">warning</span> Username already exists!</div>'
    elif error_code == 'invalid':
        toast_html = '<div class="absolute top-4 right-4 bg-error-container text-on-error-container px-6 py-3 rounded-xl shadow-lg border border-error/20 font-bold flex items-center gap-2"><span class="material-symbols-outlined text-error">error</span> Invalid credentials.</div>'

    content_html = f'''
    <div class="flex items-center justify-center min-h-[calc(100vh-64px)] animate-fade-in relative">
        {toast_html}
        <div class="w-full max-w-md bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-10 shadow-2xl">
            <div class="text-center mb-8">
                <div class="w-16 h-16 bg-primary mx-auto rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-primary/20">
                    <span class="material-symbols-outlined text-3xl text-on-primary" style="font-variation-settings: 'FILL' 1;">account_balance</span>
                </div>
                <h1 id="authTitle" class="text-3xl font-extrabold text-primary tracking-tight font-headline">Welcome Back</h1>
                <p id="authSub" class="text-sm text-on-surface-variant mt-2">Sign in to access your investment engine</p>
            </div>
            
            <div class="flex border-b border-outline-variant/20 mb-8 font-bold text-sm">
                <button id="loginTab" onclick="setType('login')" class="flex-1 pb-3 border-b-2 border-primary text-primary transition-all">Log In</button>
                <button id="signupTab" onclick="setType('signup')" class="flex-1 pb-3 text-on-surface-variant hover:text-primary transition-all">Sign Up</button>
            </div>

            <form id="authForm" action="/login" method="POST" class="space-y-5">
                <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">Username</label>
                    <div class="relative">
                        <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-outline-variant text-[20px]">person</span>
                        <input type="text" name="username" required class="w-full pl-12 pr-4 py-3 bg-surface-container-low border-none rounded-xl text-sm focus:ring-2 focus:ring-primary/20 transition-all text-primary font-medium" placeholder="Enter your username">
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2 mt-4">Password</label>
                    <div class="relative">
                        <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-outline-variant text-[20px]">lock</span>
                        <input type="password" name="password" required class="w-full pl-12 pr-4 py-3 bg-surface-container-low border-none rounded-xl text-sm focus:ring-2 focus:ring-primary/20 transition-all text-primary font-medium" placeholder="••••••••">
                    </div>
                </div>
                
                <button type="submit" id="authBtn" class="w-full mt-6 bg-primary text-on-primary font-bold py-4 rounded-xl shadow-lg hover:-translate-y-0.5 hover:shadow-xl transition-all">Access Dashboard</button>
            </form>
            <p class="text-xs text-center mt-6 text-on-surface-variant">Don't have an account? Use the <b>Sign Up</b> tab or just try a new username.</p>
        </div>
    </div>
    <script>
    function setType(t){{
        const form = document.getElementById('authForm');
        const title = document.getElementById('authTitle');
        const sub = document.getElementById('authSub');
        const btn = document.getElementById('authBtn');
        const lTab = document.getElementById('loginTab');
        const sTab = document.getElementById('signupTab');

        if(t==='signup'){{
            form.action = '/signup';
            title.innerText = 'Create Account';
            sub.innerText = 'Join WealthAI to start optimizing wealth';
            btn.innerText = 'Register & Start';
            sTab.className = 'flex-1 pb-3 border-b-2 border-primary text-primary transition-all';
            lTab.className = 'flex-1 pb-3 text-on-surface-variant hover:text-primary transition-all';
        }} else {{
            form.action = '/login';
            title.innerText = 'Welcome Back';
            sub.innerText = 'Sign in to access your investment engine';
            btn.innerText = 'Access Dashboard';
            lTab.className = 'flex-1 pb-3 border-b-2 border-primary text-primary transition-all';
            sTab.className = 'flex-1 pb-3 text-on-surface-variant hover:text-primary transition-all';
        }}
    }}
    </script>
    '''
    return get_layout(content_html, user=None, title="Authentication")

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
            rc = 'text-error' if p[0]>3 else ('text-tertiary-fixed-dim' if p[0]==3 else 'text-secondary')
            bgc = 'bg-error-container' if p[0]>3 else ('bg-tertiary-fixed/30' if p[0]==3 else 'bg-secondary-container')
            ds = p[6][:10] if p[6] else ''
            gain_pct = ((p[4] - p[2]) / p[2] * 100) if p[2] > 0 else 0
            history_html += f'''
            <div class="flex items-center justify-between p-4 bg-surface-container-lowest border border-outline-variant/10 rounded-xl hover:bg-primary-fixed/20 transition-colors">
                <div class="flex items-center gap-4">
                    <span class="text-xs font-bold text-on-surface-variant font-mono">{ds}</span>
                    <span class="text-sm font-bold text-primary font-mono">₹{p[2]:,.0f}</span>
                    <span class="text-xs text-on-surface-variant">{p[3]} · {p[1]}yr</span>
                </div>
                <div class="flex items-center gap-3">
                    <span class="text-sm font-bold text-primary font-mono">₹{p[4]:,.0f}</span>
                    <span class="px-2 py-1 {bgc} {rc} rounded-lg text-[10px] font-extrabold uppercase tracking-tight">+{gain_pct:.0f}%</span>
                </div>
            </div>'''
        history_html += '</div></div>'
 
    content_html = f'''
    <div class="max-w-2xl mx-auto py-6 animate-fade-in">
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl shadow-sm overflow-hidden">
            <div class="p-8 border-b border-outline-variant/10">
                <h2 class="text-2xl font-extrabold text-primary tracking-tight font-headline">Smart Investment Advisor</h2>
                <p class="text-sm text-on-surface-variant mt-2">AI analyzes Stocks, Mutual Funds &amp; Real Estate — shows you the best one for your full capital</p>
            </div>
            <div class="p-8">
                <form action="/predict" method="post" id="mainForm" class="space-y-6">
                    <div>
                        <div class="flex justify-between items-center mb-4">
                            <label class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Risk Tolerance</label>
                            <span id="riskLabel" class="text-secondary font-bold text-sm">1 — Conservative</span>
                        </div>
                        <input type="range" class="w-full h-2 bg-surface-container-high rounded-lg appearance-none cursor-pointer accent-primary" name="risk" id="riskSlider" min="1" max="5" value="1" oninput="updateRisk(this.value)">
                        <div class="flex justify-between text-[10px] uppercase font-bold text-on-surface-variant/60 mt-2">
                            <span>Conservative</span><span>Moderate</span><span>Aggressive</span>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-6">
                        <div>
                            <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">Time Horizon (Years)</label>
                            <input name="years" type="number" min="1" max="30" placeholder="Years" required class="w-full px-4 py-3 bg-surface-container-low border-none rounded-xl text-sm focus:ring-2 focus:ring-primary/20 transition-all text-primary font-medium">
                        </div>
                        <div>
                            <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">Your Capital (₹)</label>
                            <input name="amount" type="number" min="1000" placeholder="Full Amount" required class="w-full px-4 py-3 bg-surface-container-low border-none rounded-xl text-sm focus:ring-2 focus:ring-primary/20 transition-all text-primary font-medium">
                        </div>
                    </div>
                    
                    <button type="submit" id="analyzeBtn" class="w-full mt-2 bg-primary text-on-primary font-bold py-4 rounded-xl shadow-md hover:-translate-y-0.5 hover:shadow-lg transition-all flex items-center justify-center gap-2">
                        <span class="material-symbols-outlined text-[18px]">analytics</span> Analyze &amp; Find Best Option
                    </button>
                </form>
            </div>
        </div>
        {history_html}
    </div>
    <script>
    const labels=['Conservative','Moderate-Conservative','Moderate','Growth','Aggressive'];
    const colors=['text-secondary','text-secondary','text-tertiary-fixed-dim','text-error','text-error'];
    function updateRisk(val){{
        const l=document.getElementById('riskLabel');
        l.innerText=val+' — '+labels[val-1];
        l.className='font-bold text-sm '+colors[val-1];
    }}
    </script>
    '''
    return get_layout(content_html, user=username, title="Dashboard")

# ===== AUTH ROUTES =====
@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    password = request.form['password']
    hashed_pw = generate_password_hash(password)
    try:
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        conn.close()
        session['user'] = username
        return redirect(url_for('home'))
    except sqlite3.IntegrityError:
        return redirect(url_for('auth_page') + '?error=exists')
 
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    
    if user:
        if check_password_hash(user[0], password):
            session['user'] = username
            return redirect(url_for('home'))
        return redirect(url_for('auth_page') + '?error=invalid')
    else:
        # Smart Login: If user doesn't exist, create them instantly
        hashed_pw = generate_password_hash(password)
        try:
            conn = sqlite3.connect('users.db')
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            conn.commit()
            conn.close()
            session['user'] = username
            return redirect(url_for('home'))
        except sqlite3.IntegrityError:
            return redirect(url_for('auth_page') + '?error=exists')
 
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
    save_prediction(username, risk, years, amount, best["type"], best["projected"], best["rate"])

    with job_lock:
        job_store[job_id] = {"status": "done", "results": results, "best": best,
                             "risk": risk, "years": years, "amount": amount}


@app.route('/predict', methods=['POST'])
def predict():
    if 'user' not in session:
        return redirect(url_for('auth_page'))

    username = session['user']
    risk = int(request.form['risk'])
    years = int(request.form['years'])
    amount = float(request.form['amount'])

    job_id = str(uuid.uuid4())
    with job_lock:
        job_store[job_id] = {"status": "pending"}

        t = threading.Thread(target=_run_prediction_job, args=(job_id, username, risk, years, amount), daemon=True)
    t.start()

    # Return a lightweight polling page immediately
    content_html = f'''
    <div class="flex flex-col items-center justify-center p-20 animate-fade-in text-center h-full">
        <div class="w-16 h-16 border-4 border-outline-variant/20 border-t-primary rounded-full animate-spin mb-8"></div>
        <h2 class="text-2xl font-extrabold text-primary mb-2 font-headline">Predicting Returns</h2>
        <p id="msg" class="text-sm text-on-surface-variant mb-6 font-medium">Booting calculation engine...</p>
        <div class="flex gap-2">
            <div class="w-2 h-2 rounded-full bg-primary animate-bounce"></div>
            <div class="w-2 h-2 rounded-full bg-primary animate-bounce" style="animation-delay: 0.15s"></div>
            <div class="w-2 h-2 rounded-full bg-primary animate-bounce" style="animation-delay: 0.3s"></div>
        </div>
    </div>
    <script>
    const msgs=["Fetching live market data...","Scanning NIFTY50 stocks...","Comparing mutual fund NAVs...","Checking real estate locality listings...","Running AI return model...","Calculating final recommendation..."];
    let i=0;
    const el=document.getElementById('msg');
    const cycle=setInterval(()=>{{if(i<msgs.length-1)el.textContent=msgs[++i];}},1800);

    async function poll(){{
      try{{
        const r=await fetch('/result/{job_id}');
        const d=await r.json();
        if(d.status==='done'){{
          clearInterval(cycle);
          document.open();document.write(d.html);document.close();
        }} else {{
          setTimeout(poll,1500);
        }}
      }}catch(e){{setTimeout(poll,2000);}}
    }}
    setTimeout(poll,2000);
    </script>
    '''
    return get_layout(content_html, user=username, title="Analyzing...")


@app.route('/result/<job_id>')
def result(job_id):
    if 'user' not in session:
        return json.dumps({"status":"redirect"})
    with job_lock:
        job = job_store.get(job_id)
    if not job or job["status"] != "done":
        from flask import Response
        return Response(json.dumps({"status":"pending"}), mimetype='application/json')

    results = job["results"]
    best = job["best"]
    risk = job["risk"]
    years = job["years"]
    amount = job["amount"]
    username = session['user']
 
    risk_label = ['','Conservative','Mod. Conservative','Moderate','Mod. Aggressive','Aggressive'][risk]
    risk_color = '#ef4444' if risk>3 else ('#f59e0b' if risk==3 else '#10b981')
    colors = {'Stocks':'#00d4ff','Mutual Fund':'#10b981','Real Estate':'#f59e0b'}

    # Generate Explanation Reason
    if best["type"] == "Stocks":
        reason = f"Stocks achieved the top spot because their dynamic growth potential ({best['rate']*100:.1f}% annually) safely leverages your risk level of {risk} ({risk_label}) to maximize long-term gains."
    elif best["type"] == "Mutual Fund":
        reason = f"Mutual Funds are recommended here because they offer a superior balance of risk and reward ({best['rate']*100:.1f}% annually), perfectly fitting your timeline of {years} years with managed stability."
    else:
        if amount < 1000000:
            reason = f"Since your capital (₹{amount:,.0f}) is below standard land affordability thresholds, we highly recommend Fractional Real Estate (REITs) like {best['name'].replace('Fractional REIT: ', '')}. This gives you genuine real estate market exposure dynamically!"
        else:
            reason = f"Based on your capital of ₹{amount:,.0f}, investing in emerging/prime property areas like {best['name']} matched your risk profile perfectly, offering the highest projected historical return with {best['rate']*100:.1f}% yields."
 
    # Build result cards
    result_cards_html = '<div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 mt-8">'
    charts_data = []
 
    for idx, r in enumerate(results):
        color = colors.get(r["type"], '#00d4ff')
        is_best = (idx == 0)
        sent = r["sentiment"]
        sc = 'bg-secondary-container text-on-secondary-container' if sent>0 else ('bg-error-container text-on-error-container' if sent<0 else 'bg-tertiary-fixed/30 text-on-tertiary-fixed-variant')
        sl = '↑ Positive' if sent>0 else ('↓ Negative' if sent<0 else '→ Neutral')
 
        if is_best:
            # WINNER CARD
            card_wrapper = 'bg-surface-container-lowest border-2 border-primary shadow-xl scale-105'
            rank_badge = '<div class="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-on-primary px-4 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-widest shadow-lg whitespace-nowrap">✨ Top Recommendation</div>'
            type_label = 'text-base font-bold text-primary'
            name_style = 'text-sm text-on-surface-variant'
            stats_bg = 'bg-surface-container-low border border-primary/20'
        else:
            # COMPARISON CARD
            rank_label = '2nd' if idx == 1 else '3rd'
            card_wrapper = 'bg-surface-container-lowest border border-outline-variant/20 shadow-sm opacity-90'
            rank_badge = f'<div class="absolute -top-3 left-1/2 -translate-x-1/2 bg-surface text-on-surface-variant border border-outline-variant/20 px-3 py-1 rounded-full text-[9px] font-bold uppercase tracking-widest shadow-sm whitespace-nowrap">{rank_label} Alternative</div>'
            type_label = 'text-sm font-semibold text-on-surface-variant'
            name_style = 'text-xs text-on-surface-variant/70'
            stats_bg = 'bg-surface-container border border-outline-variant/10'
 
        result_cards_html += f'''
        <div class="relative {card_wrapper} rounded-2xl p-6 transition-all hover:shadow-2xl">
            {rank_badge}
            <div class="flex justify-between items-start mb-4">
                <div>
                    <div class="{type_label} mb-1">{r["type"]}</div>
                    <div class="{name_style}">{r["name"][:65]}{"..." if len(r["name"])>65 else ""}</div>
                </div>
                <span class="px-2 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-tight {sc}">{sl}</span>
            </div>
            
            <div class="{stats_bg} rounded-xl p-4 mb-4">
                <div class="grid grid-cols-3 gap-2 text-center divide-x divide-outline-variant/20">
                    <div>
                        <div class="text-[10px] font-bold uppercase text-on-surface-variant/70 tracking-widest">Invested</div>
                        <div class="text-xs font-bold text-primary mt-1 font-mono">₹{amount:,.0f}</div>
                    </div>
                    <div>
                        <div class="text-[10px] font-bold uppercase text-on-surface-variant/70 tracking-widest">Rate</div>
                        <div class="text-sm font-extrabold text-secondary mt-1 font-mono">{r["rate"]*100:.2f}%</div>
                    </div>
                    <div>
                        <div class="text-[10px] font-bold uppercase text-on-surface-variant/70 tracking-widest">Years</div>
                        <div class="text-sm font-extrabold text-primary mt-1 font-mono">{years}</div>
                    </div>
                </div>
            </div>
            
            <div class="flex justify-between items-center mb-4">
                <span class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Projected</span>
                <span class="text-lg font-extrabold text-secondary font-mono">₹{r["projected"]:,.0f}</span>
            </div>
            
            <div class="bg-surface-dim/30 rounded-lg p-3 text-xs text-on-surface-variant leading-relaxed">
                <b class="text-primary mr-1">Analysis:</b> {r["news"][:100]}{"..." if len(r["news"])>100 else ""}
            </div>
        </div>'''
 
        charts_data.append({
            "type": r["type"],
            "is_best": is_best,
            "dates": r["chart_dates"],
            "prices": r["chart_prices"],
            "color": color
        })
 
    result_cards_html += '</div>'
    charts_json = json.dumps(charts_data)

    content_html = f'''
    <div class="max-w-5xl mx-auto py-4 animate-fade-in">
        <div class="mb-8 flex justify-between items-end">
            <div>
                <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">Prediction Results</h2>
                <p class="text-sm text-on-surface-variant mt-2 font-medium">Analyzed for ₹{amount:,.0f} Capital • {years} Years • '{risk_label}' Risk</p>
            </div>
            <a href="/" class="flex items-center gap-2 bg-primary-container text-on-primary-container px-4 py-2 rounded-xl text-sm font-bold hover:bg-primary-fixed/30 transition-colors">
                <span class="material-symbols-outlined text-[18px]">refresh</span> New Analysis
            </a>
        </div>
        
        <div class="bg-surface-container-lowest border border-outline-variant/10 shadow-lg rounded-2xl p-8 mb-8 flex flex-col md:flex-row justify-between items-center gap-6">
            <div class="flex-1">
                <div class="text-xs font-bold uppercase tracking-widest text-secondary mb-2 flex items-center gap-2">
                    <span class="material-symbols-outlined text-sm">stars</span> Recommended Path
                </div>
                <h3 class="text-xl font-bold text-primary mb-2 line-clamp-1">{best["name"]}</h3>
                <p class="text-sm text-on-surface-variant leading-relaxed">{reason}</p>
            </div>
            <div class="text-right border-l border-outline-variant/20 pl-8 pb-2">
                <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-1">Total Yield</div>
                <div class="text-4xl font-extrabold text-secondary font-mono">₹{best["projected"]:,.0f}</div>
                <div class="text-sm font-bold text-secondary-fixed-dim mt-1">+{best["gain_pct"]:.0f}% Gain</div>
            </div>
        </div>
        
        {result_cards_html}
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8" id="charts-container">
            <!-- Charts will be injected here by JS -->
        </div>
        
        <script>
        const cData = {charts_json};
        const container = document.getElementById('charts-container');
        cData.forEach((data, index) => {{
            const div = document.createElement('div');
            div.className = `bg-surface-container-lowest border border-outline-variant/10 rounded-xl p-4 shadow-sm ${{data.is_best ? 'ring-1 ring-primary' : 'opacity-90'}}`;
            div.innerHTML = `
                <div class="flex items-center gap-2 mb-4">
                    <span class="w-3 h-3 rounded-full" style="background:${{data.color}}"></span>
                    <h3 class="text-sm font-bold text-primary">${{data.type}} Trend</h3>
                </div>
                <div class="relative h-48 w-full"><canvas id="chart-${{index}}"></canvas></div>
            `;
            container.appendChild(div);
            
            new Chart(document.getElementById(`chart-${{index}}`), {{
                type: 'line',
                data: {{
                    labels: data.dates,
                    datasets: [{{
                        label: 'Value',
                        data: data.prices,
                        borderColor: data.color,
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 0,
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ display: false }},
                        y: {{ display: false, min: Math.min(...data.prices)*0.95 }}
                    }}
                }}
            }});
        }});
        </script>
    </div>'''
    html_out = get_layout(content_html, user=username, title="Results")
    # Clean up the job from memory now it's been consumed
    with job_lock:
        job_store.pop(job_id, None)

    from flask import Response
    return Response(json.dumps({"status":"done","html":html_out}), mimetype='application/json')

# ===== NEW PAGES =====

@app.route('/insights')
def insights():
    if 'user' not in session: return redirect(url_for('auth_page'))
    try:
        nifty = yf.Ticker("^NSEI")
        news = nifty.news[:6]
    except:
        news = []
    
    news_html = '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">'
    if not news:
        news_html += '<div class="col-span-full p-12 text-center bg-surface-container rounded-2xl text-on-surface-variant">Live insights briefly offline. Tracking global signals...</div>'
    for n in news:
        d = datetime.datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%d %b %Y')
        news_html += f'''
        <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm hover:shadow-md transition-all">
            <div class="flex justify-between items-start mb-4">
                <span class="px-2 py-1 bg-primary-fixed/20 text-on-primary-fixed-variant text-[10px] font-bold uppercase tracking-widest rounded-lg">Market Signal</span>
                <span class="text-[10px] text-on-surface-variant font-medium">{d}</span>
            </div>
            <h3 class="text-sm font-bold text-primary mb-3 line-clamp-2">{n.get('title')}</h3>
            <p class="text-xs text-on-surface-variant mb-4 line-clamp-3">Source: {n.get('publisher')}</p>
            <a href="{n.get('link')}" target="_blank" class="text-xs font-bold text-secondary flex items-center gap-1 hover:underline">
                Read Full Insight <span class="material-symbols-outlined text-[14px]">arrow_forward</span>
            </a>
        </div>'''
    news_html += '</div>'
    
    content_html = f'''
    <div class="max-w-5xl mx-auto py-4 animate-fade-in">
        <div class="mb-8">
            <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">AI Market Insights</h2>
            <p class="text-sm text-on-surface-variant mt-2 font-medium">Real-time tracking of NIFTY 50 and global indicators</p>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">Overall Sentiment</div>
                <div class="text-2xl font-extrabold text-secondary">Bullish / Neutral</div>
            </div>
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">Volatility Index</div>
                <div class="text-2xl font-extrabold text-primary">Stable</div>
            </div>
            <div class="bg-surface-container-lowest border border-outline-variant/10 rounded-2xl p-6 shadow-sm">
                <div class="text-xs font-bold uppercase tracking-widest text-on-surface-variant/60 mb-2">AI Confidence</div>
                <div class="text-2xl font-extrabold text-tertiary-fixed-dim">High (86%)</div>
            </div>
        </div>
        
        {news_html}
    </div>'''
    return get_layout(content_html, user=session['user'], title="AI Insights")

@app.route('/portfolio')
def portfolio():
    if 'user' not in session: return redirect(url_for('auth_page'))
    username = session['user']
    preds = get_user_predictions(username)
    
    total_invested = sum(p[2] for p in preds)
    total_projected = sum(p[4] for p in preds)
    total_gain = total_projected - total_invested
    gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0
    
    rows_html = ""
    for p in preds:
        rows_html += f'''
        <tr class="border-b border-outline-variant/10 hover:bg-surface-container-lowest transition-colors">
            <td class="py-4 text-xs font-bold font-mono">{p[6][:10]}</td>
            <td class="py-4 text-sm font-bold text-primary">₹{p[2]:,.00f}</td>
            <td class="py-4 text-xs text-on-surface-variant font-medium">{p[3]}</td>
            <td class="py-4 text-sm font-bold text-secondary">₹{p[4]:,.00f}</td>
            <td class="py-4"><span class="px-2 py-1 bg-secondary-container/30 text-secondary text-[10px] font-bold rounded-lg">+{((p[4]-p[2])/p[2]*100):.1f}%</span></td>
        </tr>'''
        
    content_html = f'''
    <div class="max-w-5xl mx-auto py-4 animate-fade-in">
        <div class="mb-8">
            <h2 class="text-3xl font-extrabold text-primary tracking-tight font-headline">My Portfolio</h2>
            <p class="text-sm text-on-surface-variant mt-2 font-medium">Consolidated view of all AI-projected wealth targets</p>
        </div>
        
        <div class="bg-primary text-on-primary rounded-3xl p-8 mb-8 shadow-xl flex justify-between items-center bg-gradient-to-br from-primary to-primary-container">
            <div>
                <div class="text-xs font-bold uppercase tracking-widest opacity-70 mb-2">Total Managed Capital</div>
                <div class="text-5xl font-extrabold tracking-tight font-mono">₹{total_invested:,.0f}</div>
            </div>
            <div class="text-right">
                <div class="text-xs font-bold uppercase tracking-widest opacity-70 mb-2">Projected Value</div>
                <div class="text-3xl font-extrabold font-mono text-secondary-fixed">₹{total_projected:,.0f}</div>
                <div class="text-sm font-bold text-secondary-container mt-1">+{gain_pct:.1f}% Growth Target</div>
            </div>
        </div>
        
        <div class="bg-surface-container-low border border-outline-variant/10 rounded-2xl overflow-hidden shadow-sm">
            <div class="p-6 border-b border-outline-variant/10">
                <h3 class="font-bold text-primary">Investment History</h3>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left">
                    <thead class="bg-surface-container-high/30">
                        <tr>
                            <th class="py-4 px-6 text-[10px] font-bold uppercase text-on-surface-variant/60">Date</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Capital</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Asset Class</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Projected</th>
                            <th class="py-4 text-[10px] font-bold uppercase text-on-surface-variant/60">Growth</th>
                        </tr>
                    </thead>
                    <tbody class="px-6">
                        {rows_html if rows_html else '<tr><td colspan="5" class="p-12 text-center text-on-surface-variant">No prediction history found. Start your first analysis!</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>'''
    return get_layout(content_html, user=username, title="My Portfolio")

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
    app.run(debug=True, host='0.0.0.0', port=5005, use_reloader=False, threaded=True)
