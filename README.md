# WealthAI — A Data-Driven Framework For Optimized Investment Decision-Making

WealthAI is an advanced, AI-driven investment advisory framework that provides unified, real-time comparison across three major asset classes: **Stocks (NSE)**, **Mutual Funds**, and **Real Estate**. Using an "Organic Brutalist" design language, it combines high-performance background analytics with a premium user experience.

## 🚀 Key Features
- **Unified Comparison**: Simultaneously evaluate Stocks, MFs, and Real Estate based on personalized risk and timeline parameters.
- **Asynchronous Engine**: Non-blocking background workers for data scraping and model execution.
- **Machine Learning Integration**: Scikit-Learn based regression models for yield prediction.
- **AI Insights**: Market news aggregation with AI-powered sentiment analysis (Bullish/Bearish tagging).
- **Smart Login**: Frictionless authentication with automatic registration for new users.

## 🛠️ Technology Stack
- **Backend**: Python, Flask, ThreadPoolExecutor
- **Frontend**: Vanilla HTML/JS, Tailwind CSS (Custom "Organic Brutalist" system)
- **Database**: SQLite3 (optimized for concurrent access)
- **Data APIs**: YFinance, api.mfapi.in, Web Scraping (BeautifulSoup)
- **ML/Analytics**: Scikit-Learn, Pandas, Numpy, TextBlob

## 📦 Installation & Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/VemulaDhavan05/A-Data-Driven-Framework-For-Optimized-Inverstment-Decision-Making.git
    cd A-Data-Driven-Framework-For-Optimized-Inverstment-Decision-Making
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**:
    ```bash
    python app/app.py
    ```
    The app will be available at `http://localhost:5005`.

## 🧠 AI & Logic
WealthAI uses a supervised **Linear Regression** model to determine baseline expected returns. This is dynamically blended with real-time market variance to ensure recommendations are maximized for risk-adjusted yields rather than just raw historical averages.

## ⚖️ License
This project is for educational and demonstration purposes. Use at your own risk for financial decisions.
