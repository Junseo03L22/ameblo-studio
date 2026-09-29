import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path
from platformdirs import user_data_dir
from dotenv import load_dotenv
from .models import Settings, Draft


def data_dir() -> Path:
    root = Path(os.environ.get("AMEBLO_STUDIO_HOME") or user_data_dir("AmebloStudio", appauthor=False))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def setup_environment():
    # A packaged app must not read an arbitrary working directory's .env.
    load_dotenv(data_dir() / ".env", override=False)
    if not getattr(sys, "frozen", False):
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "browsers"
    if getattr(sys, "frozen", False) and bundled.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    # chmod before writing secrets, including on an existing temporary file.
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_settings() -> Settings:
    path = data_dir() / "settings.json"
    return Settings.from_dict(json.loads(path.read_text("utf-8"))) if path.exists() else Settings()


def save_settings(settings: Settings):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", settings.profile):
        raise ValueError("세션 이름은 영문·숫자·밑줄·하이픈 1~40자로 입력하세요.")
    atomic_json(data_dir() / "settings.json", asdict(settings))


def api_key(settings: Settings) -> str:
    if settings.provider == "OpenAI":
        return os.environ.get("OPENAI_API_KEY") or settings.openai_key
    return os.environ.get("GEMINI_API_KEY") or settings.gemini_key


def profile_dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        raise ValueError("유효하지 않은 세션 이름")
    folder = data_dir() / "profiles" / name
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def disable_password_storage(folder: Path):
    """Only our dedicated profile is touched; never the user's regular browser."""
    path = folder / "Default" / "Preferences"
    value = json.loads(path.read_text("utf-8")) if path.exists() else {}
    value["credentials_enable_service"] = False
    value.setdefault("profile", {})["password_manager_enabled"] = False
    atomic_json(path, value)


def save_draft(path: Path, draft: Draft):
    atomic_json(path, {"version": 1, "draft": asdict(draft)})


def load_draft(path: Path) -> Draft:
    if path.stat().st_size > 2_000_000:
        raise ValueError("초안 파일이 너무 큽니다.")
    value = json.loads(path.read_text("utf-8"))
    if value.get("version") != 1:
        raise ValueError("지원하지 않는 초안 버전입니다.")
    return Draft.from_dict(value["draft"])
