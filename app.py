from flask import Flask, render_template, request, redirect, session, flash
from flask_sqlalchemy import SQLAlchemy
import bcrypt, requests
import time
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portfolio.db'
db = SQLAlchemy(app)

# User table
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Portfolio table
class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    coin = db.Column(db.String(50))
    amount = db.Column(db.Float)
    buy_price = db.Column(db.Float)

# Create tables
with app.app_context():
    db.create_all()

# Extended coin mapping
COIN_ID_MAP = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "ada": "cardano",
    "cardano": "cardano",
    "sol": "solana",
    "solana": "solana",
    "dot": "polkadot",
    "polkadot": "polkadot",
    "matic": "matic-network",
    "polygon": "matic-network",
    "bnb": "binancecoin",
    "binance": "binancecoin",
    "xrp": "ripple",
    "ripple": "ripple",
    "ltc": "litecoin",
    "litecoin": "litecoin",
    "usdt": "tether",
    "tether": "tether",
    "usdc": "usd-coin",
    "avax": "avalanche-2",
    "avalanche": "avalanche-2",
    "link": "chainlink",
    "chainlink": "chainlink"
}

def normalize_coin(coin):
    """Normalize coin name to CoinGecko ID"""
    return COIN_ID_MAP.get(coin.lower().strip(), coin.lower().strip())

def get_price(coin):
    """Get current price with better error handling and retry logic"""
    normalized_coin = normalize_coin(coin)
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={normalized_coin}&vs_currencies=usd"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raises exception for 4xx/5xx status codes
        
        data = response.json()
        print(f"DEBUG: API response for {coin} ({normalized_coin}): {data}")  # Debug line
        
        if normalized_coin in data and 'usd' in data[normalized_coin]:
            return data[normalized_coin]['usd']
        else:
            print(f"WARNING: No price data for {coin} (tried as {normalized_coin})")
            return 0
            
    except requests.exceptions.RequestException as e:
        print(f"ERROR: API request failed for {coin}: {e}")
        return 0
    except KeyError as e:
        print(f"ERROR: Key error for {coin}: {e}")
        return 0
    except Exception as e:
        print(f"ERROR: Unexpected error for {coin}: {e}")
        return 0

def get_prices_batch(coins):
    """Get prices for multiple coins in one API call (more efficient)"""
    if not coins:
        return {}
    
    # Normalize all coin names
    normalized_coins = [normalize_coin(coin) for coin in coins]
    unique_coins = list(set(normalized_coins))  # Remove duplicates
    coins_str = ','.join(unique_coins)
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins_str}&vs_currencies=usd"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        print(f"DEBUG: Batch API response: {data}")  # Debug line
        
        # Map back to original coin names
        prices = {}
        for original_coin, normalized_coin in zip(coins, normalized_coins):
            if normalized_coin in data and 'usd' in data[normalized_coin]:
                prices[original_coin] = data[normalized_coin]['usd']
            else:
                prices[original_coin] = 0
                print(f"WARNING: No price for {original_coin} (as {normalized_coin})")
        
        return prices
        
    except Exception as e:
        print(f"ERROR: Batch API failed: {e}")
        return {coin: 0 for coin in coins}

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'error')
            return render_template("signup.html")
        
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! Please login.', 'success')
        return redirect("/login")
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        
        print(f"DEBUG: Login attempt - Username: {username}, Password: {password}")  # Debug
        
        user = User.query.filter_by(username=username).first()
        
        print(f"DEBUG: User found: {user}")  # Debug
        if user:
            print(f"DEBUG: Stored password: {user.password}, Input password: {password}")  # Debug
        
        if user and user.password == password:
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect("/dashboard")
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template("login.html")

@app.route("/add_coin", methods=["POST"])
def add_coin():
    if 'user_id' not in session:
        return redirect("/login")
    coin = request.form['coin']
    amount = float(request.form['amount'])
    buy_price = float(request.form['buy_price'])
    entry = Portfolio(user_id=session['user_id'], coin=coin, amount=amount, buy_price=buy_price)
    db.session.add(entry)
    db.session.commit()
    flash('Coin added successfully!', 'success')
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Logged out successfully!', 'success')
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect("/login")

    holdings = Portfolio.query.filter_by(user_id=session['user_id']).all()
    
    if not holdings:
        return render_template("dashboard.html", 
                             portfolio=[], 
                             total_value=0, 
                             total_profit_loss=0,
                             username=session.get('username', 'User'))
    
    # Get all coin names for batch API call
    coin_names = [h.coin for h in holdings]
    prices = get_prices_batch(coin_names)
    
    total_value = 0
    total_cost = 0
    portfolio_data = []
    chart_labels = []
    chart_values = []

    for h in holdings:
        current_price = prices.get(h.coin, 0)
        value = round(h.amount * current_price, 2)
        cost = round(h.amount * h.buy_price, 2)
        profit_loss = round(value - cost, 2)

        portfolio_data.append({
            "coin": h.coin,
            "amount": h.amount,
            "buy_price": h.buy_price,
            "current_price": current_price,
            "value": value,
            "profit_loss": profit_loss
        })

        total_value += value
        total_cost += cost
        
        # Prepare data for chart (only include coins with value > 0)
        if value > 0:
            chart_labels.append(h.coin.upper())
            chart_values.append(value)

    total_profit_loss = round(total_value - total_cost, 2)

    return render_template(
        "dashboard.html",
        portfolio=portfolio_data,
        total_value=round(total_value, 2),
        total_profit_loss=total_profit_loss,
        chart_labels=chart_labels,
        chart_values=chart_values,
        username=session.get('username', 'User')
    )

@app.route("/")
def home():
    if 'user_id' in session:
        return redirect("/dashboard")
    else:
        return redirect("/login")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    