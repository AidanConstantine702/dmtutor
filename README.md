# DMV Tutor - Flask Edition

### Quick start

```bash
git clone <this repo>
cd dmtutor
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # add your keys
flask run
```

The app runs at <http://127.0.0.1:5000>. Use Stripe test mode and your OpenAI dev key.
