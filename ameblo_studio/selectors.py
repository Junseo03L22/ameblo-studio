"""Candidate selectors; authenticated Ameblo DOM is NOT yet verified.
User overrides: app-data/selectors.json. No selectors are fetched remotely.
Ambiguous matches fail closed. Never use a generic submit button for drafts.
"""
import json
from .storage import data_dir

EDITOR_URL = "https://blog.ameba.jp/ucs/entry/srventryinsertinput.do"
DEFAULTS = {
    "title": ['input[name="entry_title"]', 'input[name="title"]', 'input[placeholder*="タイトル"]', 'textarea[placeholder*="タイトル"]'],
    "body": ['[contenteditable="true"][role="textbox"]', 'body[contenteditable="true"]', '[contenteditable="true"]'],
    "image_input": ['input[type="file"][accept*="image"]', 'input[type="file"]'],
    "image_tab": ['button:has-text("画像")', '[role="tab"]:has-text("画像")'],
    "draft_button": ['button:text-is("下書き保存")', 'button:text-is("下書きで保存")', 'input[type="submit"][value="下書き保存"]'],
    "draft_radio": ['input[type="radio"][aria-label="下書き"]', 'input[type="radio"][aria-label="下書き保存"]'],
    "public_radio": ['input[type="radio"][aria-label="全員に公開"]'],
    "submit_button": ['button:text-is("投稿する")', 'button:text-is("公開する")'],
    "draft_success": ['text="下書き保存しました"', 'text="下書きに保存しました"', 'text="下書き保存が完了しました"'],
    "public_success": ['text="記事を投稿しました"', 'text="投稿が完了しました"'],
}


def load_selectors():
    result = {k: list(v) for k, v in DEFAULTS.items()}
    path = data_dir() / "selectors.json"
    if path.exists():
        overrides = json.loads(path.read_text("utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
            raise ValueError("selectors.json에 알 수 없는 키가 있습니다.")
        for key, values in overrides.items():
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
                raise ValueError("선택자는 비어 있지 않은 문자열 배열이어야 합니다.")
            result[key] = values
    return result
