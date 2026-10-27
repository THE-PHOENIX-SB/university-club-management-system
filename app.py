# University Club Management System 
# Module 1: Registration & Login | Module 2: Membership Request & Coordinator Approval/Rejection
import sqlite3
from flask import Flask, request, redirect, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "ucms-secret"
DB = "ucms.db"


def query(sql, args=(), one=False, commit=False):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.execute(sql, args)
    rows = cur.fetchall()
    if commit:
        con.commit()
    con.close()
    return (rows[0] if rows else None) if one else rows


def setup_database():
    query("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
        password TEXT, role TEXT)""", commit=True)
    query("""CREATE TABLE IF NOT EXISTS clubs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT)""", commit=True)
    query("""CREATE TABLE IF NOT EXISTS membership_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, club_id INTEGER,
        status TEXT DEFAULT 'Pending', UNIQUE(user_id, club_id))""", commit=True)
    for name, desc in [("Dance Club", "Classical and contemporary dance"),
                       ("Drama Club", "Theatre and acting"),
                       ("Art Club", "Painting and sketching")]:
        query("INSERT OR IGNORE INTO clubs(name, description) VALUES (?,?)", (name, desc), commit=True)
    query("INSERT OR IGNORE INTO users(name,email,password,role) VALUES (?,?,?,?)",
          ("Coordinator", "coordinator@ucms.com", generate_password_hash("Coord@1234"), "Coordinator"),
          commit=True)


PAGE = """
<body style="font-family:Arial;max-width:700px;margin:30px auto">
<h2>University Club Management System</h2>
{% if session.role %}<p>Logged in as <b>{{ session.name }}</b> ({{ session.role }}) | <a href="/logout">Logout</a></p>
{% else %}<p><a href="/login">Login</a> | <a href="/register">Register</a></p>{% endif %}
{% for m in msgs %}<p style="background:#eee;padding:8px">{{ m }}</p>{% endfor %}
<hr>{{ body|safe }}</body>
"""


def show(body_template, msgs=(), **data):
    body = render_template_string(body_template, **data)
    return render_template_string(PAGE, body=body, msgs=msgs)


REGISTER_FORM = """<h3>Register</h3><form method="post" action="/register">
Name<br><input name="name" value="{{ f.get('name','') }}"><br>
Email<br><input name="email" value="{{ f.get('email','') }}"><br>
Password (min 8 chars)<br><input type="password" name="password"><br><br>
<button>Register</button></form>"""

LOGIN_FORM = """<h3>Login</h3><form method="post" action="/login">
Email<br><input name="email"><br>Password<br><input type="password" name="password"><br><br>
<button>Login</button></form>"""

STUDENT_PAGE = """<h3>Clubs</h3>
<ul>{% for c in clubs %}<li><b>{{ c.name }}</b> - {{ c.description }}</li>{% endfor %}</ul>
<h3>Request Membership</h3>
<form method="post" action="/request">
<select name="club_id"><option value="">-- Select club --</option>
{% for c in clubs %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}</select>
<button>Request Membership</button></form>
<h3>My Requests</h3>
<table border="1" cellpadding="6"><tr><th>Club</th><th>Status</th></tr>
{% for r in mine %}<tr><td>{{ r.name }}</td><td>{{ r.status }}</td></tr>{% endfor %}</table>"""

COORD_PAGE = """<h3>Membership Requests</h3>
<table border="1" cellpadding="6"><tr><th>ID</th><th>Student</th><th>Club</th><th>Status</th><th>Action</th></tr>
{% for r in rows %}<tr><td>{{ r.id }}</td><td>{{ r.student }}</td><td>{{ r.club }}</td><td>{{ r.status }}</td><td>
{% if r.status == 'Pending' %}
<form method="post" action="/decide/{{ r.id }}/approve" style="display:inline"><button>Approve</button></form>
<form method="post" action="/decide/{{ r.id }}/reject" style="display:inline"><button>Reject</button></form>
{% else %}-{% endif %}</td></tr>{% endfor %}</table>"""


# ---------------- MODULE 1: Registration & Login ----------------
@app.route("/")
def home():
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return show(REGISTER_FORM, f={})
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    pwd = request.form["password"]
    errors = []
    if not name:
        errors.append("Name is required")
    if not email:
        errors.append("Email is required")
    elif "@" not in email or "." not in email.split("@")[-1] or email.endswith("."):
        errors.append("Invalid email")
    if not pwd:
        errors.append("Password is required")
    elif len(pwd) < 8:
        errors.append("Password must be at least 8 characters")
    if not errors and query("SELECT id FROM users WHERE email=?", (email,), one=True):
        errors.append("Email already registered")
    if errors:
        return show(REGISTER_FORM, msgs=errors, f=request.form)
    query("INSERT INTO users(name,email,password,role) VALUES (?,?,?,?)",
          (name, email, generate_password_hash(pwd), "Student"), commit=True)
    return show(LOGIN_FORM, msgs=["Registration successful. Please login."])


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return show(LOGIN_FORM)
    email = request.form["email"].strip().lower()
    pwd = request.form["password"]
    if not email or not pwd:
        return show(LOGIN_FORM, msgs=["Email and password are required"])
    user = query("SELECT * FROM users WHERE email=?", (email,), one=True)
    if user and check_password_hash(user["password"], pwd):
        session.clear()
        session["user_id"], session["name"], session["role"] = user["id"], user["name"], user["role"]
        return redirect("/coordinator" if user["role"] == "Coordinator" else "/dashboard")
    return show(LOGIN_FORM, msgs=["Invalid email or password"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- MODULE 2: Membership Request & Coordinator Decision ----------------
def check_access(role):
    """Returns None if allowed, else a response (redirect to login or 403)."""
    if "user_id" not in session:
        return redirect("/login")
    if session["role"] != role:
        return "403 - Access denied", 403
    return None


@app.route("/dashboard")
def dashboard():
    blocked = check_access("Student")
    if blocked:
        return blocked
    clubs = query("SELECT * FROM clubs")
    mine = query("""SELECT c.name, r.status FROM membership_requests r
                    JOIN clubs c ON c.id=r.club_id WHERE r.user_id=?""", (session["user_id"],))
    return show(STUDENT_PAGE, clubs=clubs, mine=mine)


@app.route("/request", methods=["POST"])
def request_membership():
    blocked = check_access("Student")
    if blocked:
        return blocked
    club_id = request.form.get("club_id", "")
    msg = ""
    if not club_id:
        msg = "Please select a club"
    elif query("SELECT id FROM membership_requests WHERE user_id=? AND club_id=?",
               (session["user_id"], club_id), one=True):
        msg = "You have already requested this club"
    else:
        query("INSERT INTO membership_requests(user_id, club_id) VALUES (?,?)",
              (session["user_id"], club_id), commit=True)
        msg = "Request submitted (Pending)"
    clubs = query("SELECT * FROM clubs")
    mine = query("""SELECT c.name, r.status FROM membership_requests r
                    JOIN clubs c ON c.id=r.club_id WHERE r.user_id=?""", (session["user_id"],))
    return show(STUDENT_PAGE, msgs=[msg], clubs=clubs, mine=mine)


@app.route("/coordinator")
def coordinator():
    blocked = check_access("Coordinator")
    if blocked:
        return blocked
    rows = query("""SELECT r.id, u.name AS student, c.name AS club, r.status
                    FROM membership_requests r JOIN users u ON u.id=r.user_id
                    JOIN clubs c ON c.id=r.club_id""")
    return show(COORD_PAGE, rows=rows)


@app.route("/decide/<int:req_id>/<action>", methods=["POST"])
def decide(req_id, action):
    blocked = check_access("Coordinator")
    if blocked:
        return blocked
    status = "Approved" if action == "approve" else "Rejected"
    query("UPDATE membership_requests SET status=? WHERE id=? AND status='Pending'",
          (status, req_id), commit=True)
    return redirect("/coordinator")


if __name__ == "__main__":
    setup_database()
    app.run(debug=True)
