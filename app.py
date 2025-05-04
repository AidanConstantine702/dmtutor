import os, json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import json, random, pathlib
QUESTIONS = json.load(open(pathlib.Path(__file__).with_name("dmv_questions.json"), encoding="utf-8"))

# Third‑party APIs
import openai, stripe

# ------------------ FREE PASSCODE ------------------
PASSCODE = "DMTUTOR070207"

load_dotenv()  # .env file

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///dmv.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize libs
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Configure external APIs
openai.api_key = os.getenv("OPENAI_API_KEY")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ---------- Models ----------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_active_subscriber = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    score = db.Column(db.Integer)
    total = db.Column(db.Integer)

# --- create tables at import time when running on Render ---
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Routes ----------
@app.route("/")
def home():
    return render_template("home.html")

# Auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].lower()
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return redirect(url_for("register"))
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

# Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    results = QuizResult.query.filter_by(user_id=current_user.id).all()
    return render_template("dashboard.html", results=results)

# ---------- Take a quiz ----------
@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    # ----- paywall guard -----
    if not current_user.is_active_subscriber:
        flash("🚀  Access locked! Buy lifetime access for $30 or use your passcode.", "error")
        return redirect(url_for("dashboard"))

    # ----- handle form submission -----
    if request.method == "POST":
        answers = json.loads(request.form["answers"])
        score = sum(int(request.form.get(f"q{idx}", -1)) == ans for idx, ans in answers.items())
        result = QuizResult(user_id=current_user.id, score=score, total=10)
        db.session.add(result); db.session.commit()
        return render_template("result.html", score=score, total=10)

    # ----- GET: pick 10 fresh questions -----
    quiz = random.sample(QUESTIONS, 10)
    answers = {i: q["answer"] for i, q in enumerate(quiz)}
    return render_template("quiz.html", quiz=quiz, answers=json.dumps(answers))

# ---------- Stripe checkout (one‑time $30 purchase) ----------
@app.route("/create_checkout_session", methods=["POST"])   # ← USE underscore, not fancy dash
@login_required
def create_checkout_session():
    YOUR_DOMAIN = request.host_url.rstrip("/")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 3000,  # $30.00  (3 000 cents)
                    "product_data": {"name": "DMV Tutor – Lifetime Access"},
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=f"{YOUR_DOMAIN}/dashboard?success=true",
        cancel_url=f"{YOUR_DOMAIN}/dashboard?canceled=true",
        metadata={"user_id": current_user.id},
    )
    return jsonify({"url": session.url})


# ---------- Unlock via passcode ----------
@app.route("/unlock-passcode", methods=["POST"])
@login_required
def unlock_passcode():
    code = request.form.get("code", "").strip()
    if code == PASSCODE:
        current_user.is_active_subscriber = True
        db.session.commit()
        flash("✅  Access unlocked! Enjoy DMV Tutor.", "success")
    else:
        flash("❌  Invalid code. Please try again.", "error")
    return redirect(url_for("dashboard"))

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 3000,  # 3 000 cents = $30.00
                    "product_data": {
                        "name": "DMV Tutor – Lifetime Access"
                    },
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=f"{YOUR_DOMAIN}/dashboard?success=true",
        cancel_url=f"{YOUR_DOMAIN}/dashboard?canceled=true",
        metadata={"user_id": current_user.id}
    )
    return jsonify({"url": session.url})

# Stripe webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    try:
        event = checkout.session.completed_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return str(e), 400
    if event["type"] == "checkout.session.completed":
        user_id = event["data"]["object"]["metadata"]["user_id"]
        user = User.query.get(int(user_id))
        if user:
            user.is_active_subscriber = True
            db.session.commit()
    return "", 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
