import re
import json
import requests

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from flask import Markup
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
# app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
# app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get portfolio from database
    portfolio = db.execute("SELECT stock, SUM(shares) FROM transactions WHERE UserID = :userid GROUP BY stock", userid = session["user_id"])
    # Declare a list for storing stock info
    portfolioList = []
    # Declare a variable to store the total value of each stock based on the total shares the user owns
    stockTotal = 0
    # Iterate over each row from the database and extract the required information for our table
    for row in portfolio:
        portfolioList.append(
                {
                    "stock" : row['stock'],
                    "name" : lookup(row['stock'])['name'],
                    "shares" : row['SUM(shares)'],
                    "price" : usd(lookup(row['stock'])['price']),
                    "total" : usd(lookup(row['stock'])['price'] * row['SUM(shares)'])
                }
            )
            # Add to the stock total
        stockTotal = stockTotal + lookup(row['stock'])['price'] * row['SUM(shares)']
    # Retrieve the amount of cash the user has
    userFunds = db.execute("SELECT cash FROM users WHERE id = :userid", userid=session["user_id"])[0]['cash']
    # Calculate their portfolio total
    totalFunds = stockTotal + userFunds
    # Load our table (index.html)
    return render_template("index.html", portfolioList=portfolioList, userFunds = usd(userFunds), totalFunds = usd(totalFunds))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # If form is submitted
    if request.method == "POST":

        # Ensure the user provides a stock
        if not request.form.get("shares"):
            flash(u"Missing share amount", "error")
            return render_template("buy.html")

        # Match API with provided stock symbol
        stocks = lookup(request.form.get("stock"))

        # If no such stock exists
        if not stocks or not stocks['name']:
            flash(u"No such stock!", "error")
            return render_template("buy.html")

        # Retrieve all necessary stock info from API
        purchaseTotal = stocks["price"] * int(request.form.get("shares"))

        # Make sure user has enough money
        userFunds = db.execute("SELECT cash FROM users WHERE id = :userid", userid=session["user_id"])[0]['cash']
        if userFunds < purchaseTotal:
            # Error message and stay on same page
            flash(u"Not enough cash! ({0}) remaning in your account.".format(usd(userFunds)))
            return render_template("buy.html")
        # If enough cash then log the transaction
        db.execute("INSERT INTO transactions (userID, stock, shares, price, stockPrice) VALUES (:userID, :stock, :shares, :price, :stockPrice)",
            userID = session["user_id"], stock = stocks["symbol"], shares = request.form.get("shares"), price = purchaseTotal, stockPrice = stocks["price"])
        # And update the users cash total
        db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash = userFunds - purchaseTotal, userid = session["user_id"])

        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT stock, shares, stockPrice, Timestamp FROM transactions WHERE UserID = :userid", userid = session["user_id"])
    # Declare a list for storing stock info
    historyList = []
    # Iterate over each row from the database and extract the required information for our table
    for row in history:
        historyList.append(
                {
                    "stock" : row['stock'],
                    "shares" : row['shares'],
                    "price" : row['stockPrice'],
                    "date" : row['Timestamp']
                }
            )
    return render_template("history.html", historyList=historyList)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
# @login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # If the user doesn't provide a stock
        if not request.form.get("stock"):
            # Error message and reload page
            flash(u"Please provide a stock symbol", "error")
            return render_template("quote.html")
        # Lookup the stock in the API
        stocks = lookup(request.form.get("stock"))
        # If not found / flash error message and reload
        if not stocks or not stocks['name']:
            flash(u"No such stock!", "error")
            return render_template("quote.html")
        # If found - get the price and display it in USD
        price = (usd(stocks['price']))
        return render_template("quoted.html", stocks=stocks, price=price)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Source (https://www.geeksforgeeks.org/password-validation-in-python/)
    reg = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&-_])[A-Za-z\d@$!#%*?&-_]{6,20}$"
    if request.method == "POST":
        username=request.form.get("username")
        # Compile Regex
        pat = re.compile(reg)
        # Search Regex
        mat = re.search(pat, request.form.get("password"))
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure the passwords match
        elif request.form.get("password") != request.form.get("passwordConfirm"):
            return apology("passwords must match", 403)

        # Ensure the password meets requirements
        elif not mat:
            return apology("passwords must meet requirements", 403)

        # Ensure username doesn't exist already
        rows = db.execute("SELECT * FROM users WHERE username = :username",
            username=request.form.get("username"))
        if len(rows) == 1:
            return apology("username unavailable", 403)
        # Hash the password
        hashed = generate_password_hash(request.form.get("password"))
        # Insert user info into users
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashed)", username=username,hashed=hashed)
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        # Ensure the user provides an amount to sell
        if not request.form.get("shares"):
            flash(u"Missing share amount", "error")
            return render_template("sell.html")

        # Match API with provided stock symbol
        stocks = lookup(request.form.get("stock"))

        # Retrieve all necessary stock info from API
        sellTotal = stocks["price"] * int(request.form.get("shares"))

        # Retrieve users funds
        userFunds = db.execute("SELECT cash FROM users WHERE id = :userid", userid=session["user_id"])[0]['cash']

        # Retrieve the users share total for the selected stock
        totalShares = db.execute("SELECT stock, SUM(shares) FROM transactions WHERE UserID = :userid GROUP BY stock", userid = session["user_id"])

        for x in totalShares:
            if x["stock"] == request.form.get("stock"):
                if x['SUM(shares)'] < int(request.form.get("shares")):
                    flash("You only own {0} share(s)".format(x['SUM(shares)']))
                    return apology("invalid share amount", 403)
        # If enough cash then log the transaction
        db.execute("INSERT INTO transactions (userID, stock, shares, price, stockPrice) VALUES (:userID, :stock, :shares, :price, :stockPrice)",
            userID = session["user_id"], stock = stocks["symbol"], shares = -int(request.form.get("shares")), price = sellTotal, stockPrice = stocks["price"])
        # And update the users cash total
        db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash = userFunds + sellTotal, userid = session["user_id"])

        return redirect("/")

    else:
        # Populate dropdown menu with the stocks the user owns
        userStocks = db.execute("SELECT stock, SUM(shares) FROM transactions WHERE UserID = :userid GROUP BY stock", userid = session["user_id"])
        userStocksList = []
        for y in userStocks:
            if y["SUM(shares)"] > 0:
                userStocksList.append(y["stock"])
        return render_template("sell.html", userStocks = userStocksList)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# if __name__ == '__main__':
#     # Threaded option to enable multiple instances for multiple user access support
#     app.run(threaded=True, port=5000)