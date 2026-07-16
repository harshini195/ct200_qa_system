from dotenv import load_dotenv

# Must run here, not in main.py: database.py, llm_client.py, and
# json_store.py all read os.environ.get(...) at module import time (to set
# DB_PATH / GROQ_API_KEY / STORE_DIR as module-level constants). Since this
# package's __init__.py is imported before any of its submodules, loading
# .env here -- rather than at the top of main.py -- guarantees those reads
# see the values from .env instead of only picking up variables that
# happen to already be in the shell environment.
load_dotenv()
