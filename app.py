import os, json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Third‑party APIs
import openai, stripe

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

# Quiz
@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    if request.method == "POST":
        # Front‑end sends user's answers; calculate score
        submitted = request.json.get("answers", [])
        correct = request.json.get("correct", [])
        score = sum(1 for s, c in zip(submitted, correct) if s == c)
        result = QuizResult(user_id=current_user.id, score=score, total=len(correct))
        db.session.add(result)
        db.session.commit()
        return jsonify({"score": score})
    else:
        # Generate questions via OpenAI
        prompt = (
            "Generate 10 multiple‑choice questions (A, B, C, D) about the "
            "South Carolina DMV permit test. Respond as strict JSON array with "
            "objects: question, choices (list), answer (letter)."
        )
        try:
            completion = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            qjson = json.loads(completion.choices[0].message.content)
        except Exception as e:
            # Fallback hard‑coded sample
            qjson = [
                {
                    "question": "What is the legal BAC limit for drivers under 21 in South Carolina?",
                    "choices": ["0.00%", "0.02%", "0.05%", "0.08%"],
                    "answer": "B"
                }
            ] * 10
        return render_template("quiz.html", quiz=qjson)

# Stripe checkout (bare‑bones)
@app.route("/create‑checkout‑session", methods=["POST"])
@login_required
def create_checkout_session():
    YOUR_DOMAIN = request.host_url.rstrip("/")
    session = stripe.checkout.Session.create(
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 799,  # $7.99 monthly
                    "product_data": {"name": "DMV Tutor Monthly Subscription"},
                },
                "quantity": 1,
            }
        ],
        mode="subscription",
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
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
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
