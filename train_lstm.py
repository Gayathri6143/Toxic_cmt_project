import re
import pickle
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense, Dropout
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.callbacks import EarlyStopping

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "model"
MODEL_DIR.mkdir(exist_ok=True)

DATA_PATH = BASE_DIR / "toxic.csv"
MODEL_PATH = MODEL_DIR / "lstm_model.keras"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.pkl"
LABEL_INFO_PATH = MODEL_DIR / "label_info.pkl"
METRICS_PATH = MODEL_DIR / "metrics.pkl"

MAX_WORDS = 5000
MAX_LEN = 30
EMBED_DIM = 64

def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

df = pd.read_csv(DATA_PATH)
df["comment_text"] = df["comment_text"].astype(str).apply(clean_text)
df["toxic"] = df["toxic"].astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    df["comment_text"],
    df["toxic"],
    test_size=0.2,
    random_state=42,
    stratify=df["toxic"]
)

tokenizer = Tokenizer(num_words=MAX_WORDS, oov_token="<OOV>")
tokenizer.fit_on_texts(X_train)

X_train_seq = tokenizer.texts_to_sequences(X_train)
X_test_seq = tokenizer.texts_to_sequences(X_test)

X_train_pad = pad_sequences(X_train_seq, maxlen=MAX_LEN, padding="post", truncating="post")
X_test_pad = pad_sequences(X_test_seq, maxlen=MAX_LEN, padding="post", truncating="post")

model = Sequential([
    Embedding(input_dim=MAX_WORDS, output_dim=EMBED_DIM, input_length=MAX_LEN),
    LSTM(64, dropout=0.2, recurrent_dropout=0.2),
    Dense(32, activation="relu"),
    Dropout(0.3),
    Dense(1, activation="sigmoid")
])

model.compile(
    optimizer="adam",
    loss="binary_crossentropy",
    metrics=["accuracy"]
)

early_stop = EarlyStopping(
    monitor="val_loss",
    patience=3,
    restore_best_weights=True
)

model.fit(
    X_train_pad,
    y_train,
    validation_split=0.2,
    epochs=10,
    batch_size=8,
    callbacks=[early_stop],
    verbose=1
)

y_pred_prob = model.predict(X_test_pad, verbose=0)
y_pred = (y_pred_prob >= 0.5).astype(int).flatten()

acc = accuracy_score(y_test, y_pred)
report = classification_report(y_test, y_pred)

print("Accuracy:", acc)
print(report)

model.save(MODEL_PATH)

with open(TOKENIZER_PATH, "wb") as f:
    pickle.dump(tokenizer, f)

with open(LABEL_INFO_PATH, "wb") as f:
    pickle.dump({"max_len": MAX_LEN}, f)

with open(METRICS_PATH, "wb") as f:
    pickle.dump({
        "accuracy_percent": acc * 100
    }, f)

print("LSTM model and metrics saved successfully.")