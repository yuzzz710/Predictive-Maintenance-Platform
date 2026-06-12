"""
Configuration — paths, API keys, model settings.
All sensitive values come from environment variables or .env file.
"""
import os
from pathlib import Path

# ── Load .env ──
try:
    from dotenv import load_dotenv
except ImportError:
    print("[ERROR] python-dotenv not installed. Run: pip install python-dotenv")
    import sys
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent          # web-dashboard/
PROJECT_ROOT = BASE_DIR.parent                              # git5/

env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"[config] Loaded .env from {env_path}")
else:
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[config] Loaded .env from {env_path}")
    else:
        print(f"[WARNING] .env file not found at {BASE_DIR / '.env'} or {PROJECT_ROOT / '.env'}")
        print("[WARNING] Set DEEPSEEK_API_KEY environment variable or create a .env file.")
MCP_DIR = PROJECT_ROOT / "agent-mcp架构"
DATA_DIR = PROJECT_ROOT / "原始数据集"
V3_OUTPUTS = PROJECT_ROOT / "预测性维护模型_v3" / "outputs"
DASHBOARD_DATA = BASE_DIR / "data"                          # precomputed CSVs
OUTPUTS_DIR = BASE_DIR / "outputs"                          # runtime outputs

# ── DeepSeek API ──
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# ── Server ──
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8765"))
