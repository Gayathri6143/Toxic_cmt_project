from flask import Flask, render_template, request, jsonify
import sqlite3
import pickle
import pandas as pd
import re
from pathlib import Path

from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
WORDS_PATH = BASE_DIR / "words.csv"
MODEL_PATH = BASE_DIR / "model" / "lstm_model.keras"
TOKENIZER_PATH = BASE_DIR / "model" / "tokenizer.pkl"
LABEL_INFO_PATH = BASE_DIR / "model" / "label_info.pkl"
METRICS_PATH = BASE_DIR / "model" / "metrics.pkl"

TOXIC_THRESHOLD = 0.70

model = load_model(MODEL_PATH)

with open(TOKENIZER_PATH, "rb") as f:
    tokenizer = pickle.load(f)

with open(LABEL_INFO_PATH, "rb") as f:
    label_info = pickle.load(f)

MAX_LEN = int(label_info["max_len"])

accuracy_percent = 0.0
if METRICS_PATH.exists():
    with open(METRICS_PATH, "rb") as f:
        metrics = pickle.load(f)
        accuracy_percent = float(metrics.get("accuracy_percent", 0.0))

df_words = pd.read_csv(WORDS_PATH).fillna("")
replacement = dict(
    zip(
        df_words["bad_word"].astype(str).str.strip().str.lower(),
        df_words["good_word"].astype(str).str.strip()
    )
)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            receiver TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def find_replacements(text):
    suggestions = []
    source = str(text)

    for bad_word, good_word in replacement.items():
        pattern = re.compile(rf"\b{re.escape(bad_word)}\b", re.IGNORECASE)
        if pattern.search(source):
            suggestions.append({
                "bad_word": bad_word,
                "good_word": good_word
            })

    return suggestions

def apply_replacements(text):
    updated_text = str(text)

    for bad_word, good_word in replacement.items():
        pattern = re.compile(rf"\b{re.escape(bad_word)}\b", re.IGNORECASE)
        updated_text = pattern.sub(good_word, updated_text)

    return updated_text

def predict_toxicity(text):
    cleaned = clean_text(text)

    if not cleaned:
        return False, 0.0

    seq = tokenizer.texts_to_sequences([cleaned])
    padded = pad_sequences(seq, maxlen=MAX_LEN, padding="post", truncating="post")
    prob = float(model.predict(padded, verbose=0)[0][0])

    return prob >= TOXIC_THRESHOLD, prob

init_db()

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"status": "fail", "message": "Username and password are required."}), 400

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO users(username, password) VALUES(?, ?)",
            (username, password)
        )
        conn.commit()
        return jsonify({"status": "ok"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "exists", "message": "Username already exists."}), 409
    finally:
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    conn = get_db_connection()
    user = conn.execute(
        "SELECT username FROM users WHERE username=? AND password=?",
        (username, password)
    ).fetchone()
    conn.close()

    if user:
        return jsonify({"status": "ok", "username": user["username"]})

    return jsonify({"status": "fail", "message": "Invalid username or password."}), 401

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(force=True)
    text = data.get("message", "")

    if not text.strip():
        return jsonify({
            "toxic": False,
            "probability": 0.0,
            "suggestions": [],
            "clean_text": "",
            "can_send": False
        })

    suggestions = find_replacements(text)
    model_toxic, probability = predict_toxicity(text)

    can_send = (len(suggestions) == 0 and not model_toxic)

    return jsonify({
        "toxic": model_toxic or len(suggestions) > 0,
        "probability": round(probability, 4),
        "suggestions": suggestions,
        "clean_text": apply_replacements(text),
        "can_send": can_send
    })

@app.route("/send", methods=["POST"])
def send_message():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    receiver = data.get("receiver", "").strip()
    message = data.get("message", "").strip()

    if not username or not receiver or not message:
        return jsonify({"status": "fail", "message": "Missing required fields."}), 400

    suggestions = find_replacements(message)
    model_toxic, probability = predict_toxicity(message)

    if suggestions or model_toxic:
        return jsonify({
            "status": "blocked",
            "message": "Replace toxic words before sending.",
            "probability": round(probability, 4),
            "suggestions": suggestions,
            "clean_text": apply_replacements(message)
        }), 400

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO chats(username, receiver, message) VALUES(?, ?, ?)",
            (username, receiver, message)
        )
        conn.commit()

        rows = conn.execute(
            """
            SELECT username, receiver, message, created_at
            FROM chats
            WHERE (username=? AND receiver=?) OR (username=? AND receiver=?)
            ORDER BY id ASC
            """,
            (username, receiver, receiver, username)
        ).fetchall()
    finally:
        conn.close()

    messages = []
    for row in rows:
        messages.append({
            "sender": row["username"],
            "receiver": row["receiver"],
            "message": row["message"],
            "created_at": row["created_at"]
        })

    return jsonify({"status": "ok", "messages": messages})

@app.route("/messages/<username>/<receiver>", methods=["GET"])
def get_messages(username, receiver):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT username, receiver, message, created_at
            FROM chats
            WHERE (username=? AND receiver=?) OR (username=? AND receiver=?)
            ORDER BY id ASC
            """,
            (username, receiver, receiver, username)
        ).fetchall()
    finally:
        conn.close()

    messages = []
    for row in rows:
        messages.append({
            "sender": row["username"],
            "receiver": row["receiver"],
            "message": row["message"],
            "created_at": row["created_at"]
        })

    return jsonify({"status": "ok", "messages": messages})

@app.route("/accuracy", methods=["GET"])
def accuracy():
    return jsonify({
        "accuracy_percent": round(accuracy_percent, 2)
    })

if __name__ == "__main__":
    app.run(debug=True)