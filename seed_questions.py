import json, sqlite3
from pathlib import Path

DB = Path("dmv_questions.db")

QUESTIONS = [
    # ----‑‑‑‑‑‑‑‑ SAMPLE QUESTIONS (keep these 2) ----
    {
        "question": "Alcohol and other impairing drugs ______.",
        "choices": ["reduce your judgment", "decrease your reaction time", "improve your ability to focus"],
        "answer": 0
    },
    {
        "question": "A yellow dashed line on your side of the roadway only means:",
        "choices": ["passing is prohibited on both sides",
                    "passing is permitted on both sides",
                    "passing is permitted on your side"],
        "answer": 2
    },
    # 👉 Add 248 more Q‑and‑A blocks here later
]

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            choices TEXT NOT NULL,
            answer INTEGER NOT NULL
        )
        """
    )
    cur.executemany(
        "INSERT INTO quiz_question (question, choices, answer) VALUES (?,?,?)",
        [(q["question"], json.dumps(q["choices"]), q["answer"]) for q in QUESTIONS],
    )
    conn.commit(); conn.close()
    print(f"Seeded {len(QUESTIONS)} questions into {DB}")

if __name__ == "__main__":
    main()