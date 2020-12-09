import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from functools import wraps
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from bs4 import BeautifulSoup
import requests


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
    

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///nba.db")


searchresult = [None] * 3


def login_required(f):
    # Decorate routes to require login.
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function
    

@app.route("/star", methods=["GET", "POST"])
@login_required
def starswitch():
    if request.method == "POST":
        name = request.form.get("starselect")
        starresults = db.execute("SELECT name, star FROM account WHERE user_id = :user_id AND name=:name",
                                 user_id=session["user_id"], name=name)
        # Adding favorite
        if starresults[0]["star"] == 0:
            total = db.execute("SELECT star FROM account WHERE user_id = :user_id AND star = 1",
                               user_id=session["user_id"])
            # Check for maximum limit of favorite players
            if len(total) < 5:
                db.execute("UPDATE account SET star = 1 WHERE user_id=:user_id AND name=:name",
                           user_id=session["user_id"], name=name)
            else:
                flash("You cannot have more than 5 favorited players")

        else:
            # Removing favorite
            db.execute("UPDATE account SET star = 0 WHERE user_id=:user_id AND name=:name",
                       user_id=session["user_id"], name=name)
    return redirect("/")


@app.route("/favorite")
@login_required
def favorite():
    # Select favorited players
    stars = db.execute("SELECT * FROM account WHERE user_id = :user_id AND star = 1",
                       user_id=session["user_id"])
    return render_template("favorite.html", stars=stars)
    

@app.route("/delete", methods=["GET", "POST"])
@login_required
def delete():
    if request.method == "POST":
        # Delete player from account
        name = request.form.get("deleteplayer")
        db.execute("DELETE FROM account WHERE user_id = :user_id AND name = :name",
                   user_id=session["user_id"], name=name)
        flash(name + " has been deleted from your account")
    return redirect("/")
    

@app.route("/logos", methods=["GET", "POST"])
@login_required
def logos():
    if request.method == "POST":
        status = 0
        name = (request.form.get("search")).replace(" ", "+")
        # Search link
        query = ("https://www.basketball-reference.com/search/search.fcgi?search=" + name)
        if requests.head(query).status_code == 302:
            status = 1
        if status == 0:
            # Checking search link for result
            source = requests.get(query).text
            soup = BeautifulSoup(source, 'lxml')
            try:
                link = soup.find('div', class_='search-item-url').text
                acronym = link.split("/")[2]
                team = soup.find('div', class_='search-item-name').strong.text
                team = team.split(" (")[0]
            except:
                flash("No results were found")
                return redirect("/logos")
        else:
            link = requests.head(query, allow_redirects=True).url
            acronym = link.split("/")[4]
            source = requests.get(query).text
            soup = BeautifulSoup(source, 'lxml')
            team = soup.find('h1').span.text
        # Anomalies
        if acronym == "PHO":
            acronym = "PHX"
        elif acronym == "NJN":
            acronym = "BKN"
        elif acronym == "NOH":
            acronym = "NOP"
        imglink = ("http://global.nba.com/media/img/teams/logos/" + acronym + "_logo.svg")
        if requests.head(imglink).status_code == 404:
            flash("No results were found")
            return render_template("logos.html", imglink='"data:," alt', team="")
        return render_template("logos.html", imglink=imglink, team=team)
    else:
        return render_template("logos.html", imglink='"data:," alt', team="")


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    if request.method == "POST":
        global searchresult
        status = 0
        name = (request.form.get("search")).replace(" ", "+")
        # Search link
        query = ("https://www.basketball-reference.com/search/search.fcgi?search=" + name)
        if requests.head(query).status_code == 302:
            status = 1
        if status == 0:
            # Checking search link for result
            source = requests.get(query).text
            soup = BeautifulSoup(source, 'lxml')
            try:
                searchresult[2] = soup.find('div', class_='search-item-url').text
            except:
                flash("No results were found")
                return redirect("/")
            searchresult[2] = ("https://www.basketball-reference.com" + searchresult[2])
            imgsource = requests.get(searchresult[2]).text
        else:
            imgsource = requests.get(query).text
            searchresult[2] = query
        imgsoup = BeautifulSoup(imgsource, 'lxml')
        searchresult[0] = imgsoup.find('h1').span.text
        if imgsoup.find('div', class_='media-item') == None:
            searchresult[1] = '"data:," alt'
        else:
            searchresult[1] = imgsoup.find('div', class_='media-item').img['src']
        return render_template("add.html", searchresult=searchresult)
    else:
        return redirect("/")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        searchname = db.execute("SELECT name FROM account WHERE user_id = :user_id AND name=:name",
                                user_id=session["user_id"], name=searchresult[0])
        if not searchname:
            # Datascrape stats from basketball reference
            source = BeautifulSoup(requests.get(searchresult[2]).text, 'lxml')
            if source.find('table', {"id": "per_game"}) == None:
                points = assists = rebounds = "N/A"
            else:
                pergame = source.find('table', {"id": "per_game"}).tfoot
                points = pergame.find('td', {"data-stat": "pts_per_g"}).text
                assists = pergame.find('td', {"data-stat": "ast_per_g"}).text
                rebounds = pergame.find('td', {"data-stat": "trb_per_g"}).text
            
            # Insert player into account
            db.execute('''INSERT INTO account (user_id, name, image, link, points, assists, rebounds)
                        VALUES (:user_id, :name, :image, :link, :points, :assists, :rebounds)''',
                       user_id=session["user_id"], name=searchresult[0], image=searchresult[1], link=searchresult[2],
                       points=points, assists=assists, rebounds=rebounds)
            flash(searchresult[0] + " has been added to your account")
        else:
            flash(searchname[0] + " is already in your account")
        return redirect("/")
    else:
        # Get players from account
        playertable = db.execute("SELECT * FROM account WHERE user_id = :user_id",
                                 user_id=session["user_id"])
        playerdata = []

        for row in playertable:
            name = row["name"]
            image = row["image"]
            link = row["link"]
            star = row["star"]
            playerdata.append({"name": name, "image": image, "link": link, "star": star})

        return render_template("index.html", playerdata=playerdata)


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":

        required = [None] * 8
        errormessage = "This field is required"

        # Check if it is blank
        if not request.form.get("username"):
            required[0] = "required"
            return render_template("account.html", required=required, errormessage=errormessage)

        # Query username and hash data
        check = db.execute("SELECT username, hash FROM users WHERE id = :user_id",
                           user_id=session["user_id"])

        if request.form.get("username") != check[0]["username"]:
            required[1] = "required"
            return render_template("account.html", required=required)

        # Check if old password is blank
        if not request.form.get("oldpassword"):
            required[2] = "required"
            return render_template("account.html", required=required, errormessage=errormessage)

        # Check if old passwords match
        if not check_password_hash(check[0]["hash"], request.form.get("oldpassword")):
            required[3] = "required"
            return render_template("account.html", required=required)

        # Check if password is blank
        if not request.form.get("newpassword"):
            required[4] = "required"
            return render_template("account.html", required=required, errormessage=errormessage)

        # Check if new password is new
        if request.form.get("oldpassword") == request.form.get("newpassword"):
            required[5] = "required"
            return render_template("account.html", required=required)

        if not request.form.get("confirmation"):
            required[6] = "required"
            return render_template("account.html", required=required, errormessage=errormessage)

        # Check if passwords match
        if request.form.get("newpassword") != request.form.get("confirmation"):
            required[7] = "required"
            return render_template("account.html", required=required)

        # Update password in database
        db.execute("UPDATE users SET hash = :newhash WHERE id = :user_id",
                   newhash=generate_password_hash(request.form.get("newpassword")),
                   user_id=session["user_id"])

        flash("Password updated")

        return redirect("/")

    else:
        required = [None] * 8
        
        # Get count of total players and favorite players
        total = db.execute("SELECT COUNT(*) FROM account WHERE user_id=:user_id",
                           user_id=session["user_id"])
        stars = db.execute("SELECT COUNT(*) FROM account WHERE user_id=:user_id AND star = 1",
                           user_id=session["user_id"])
        total = total[0]["COUNT(*)"]
        stars = stars[0]["COUNT(*)"]
        return render_template("account.html", required=required, total=total, stars=stars)


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        required = [None] * 5
        errormessage = "This field is required"

        # Check if it is blank
        if not request.form.get("username"):
            required[0] = "required"
            return render_template("register.html", required=required, errormessage=errormessage)

        # Query database for already existing username
        check = db.execute("SELECT * FROM users WHERE username = :username",
                           username=request.form.get("username"))

        # Check if username exists
        if len(check) != 0:
            required[1] = "required"
            return render_template("register.html", required=required)

        # Check if password is blank
        if not request.form.get("password"):
            required[2] = "required"
            return render_template("register.html", required=required, errormessage=errormessage)

        # Check if confirmed password is blank
        if not request.form.get("confirmation"):
            required[3] = "required"
            return render_template("register.html", required=required, errormessage=errormessage)

        # Check if passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            required[4] = "required"
            return render_template("register.html", required=required)

        # Insert user into database
        username = request.form.get("username")
        hashed = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashed)",
                   username=username, hashed=hashed)

        # Remember which user has logged in
        session["user_id"] = db.execute("SELECT id FROM users WHERE username = :username",
                                        username=username)[0]["id"]

        flash("Registered")

        return redirect("/")

    else:
        required = [None] * 5
        return render_template("register.html", required=required)


@app.route("/login", methods=["GET", "POST"])
def login():

    # Forget any user_id
    session.clear()

    required = [None] * 3

    errormessage = "This field is required"

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            required[0] = "required"
            return render_template("login.html", required=required, errormessage=errormessage)

        # Ensure password was submitted
        elif not request.form.get("password"):
            required[1] = "required"
            return render_template("login.html", required=required, errormessage=errormessage)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            required[2] = "required"
            return render_template("login.html", required=required)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        required = [None] * 3
        return render_template("login.html", required=required)


@app.route("/logout")
def logout():

    # Forget any user_id
    session.clear()

    return redirect("/")