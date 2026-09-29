import threading
import pytest
from playwright.sync_api import sync_playwright
from ameblo_studio.publisher import locate, submit, editor_html, verify_editor, run_browser, remote_url
from ameblo_studio.selectors import DEFAULTS
from ameblo_studio.models import Draft, Brief, Template, ImagePlacement
from ameblo_studio.content import demo_copy, render_html


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.mark.browser
def test_draft_never_clicks_public_button(page):
    page.set_content('''<button onclick="window.action='public'">公開する</button>
        <button onclick="window.action='draft'">下書き保存</button>''')
    submit(page, DEFAULTS, publish=False)
    assert page.evaluate("window.action") == "draft"


@pytest.mark.browser
def test_missing_draft_fails_closed(page):
    page.set_content('''<button onclick="window.action='public'">公開する</button>''')
    with pytest.raises(RuntimeError):
        submit(page, DEFAULTS, publish=False)
    assert page.evaluate("window.action") is None


@pytest.mark.browser
def test_draft_radio_checked_before_submit(page):
    page.set_content('''<input type="radio" name="mode" aria-label="下書き">
        <button onclick="window.draft=document.querySelector('input').checked">投稿する</button>''')
    submit(page, DEFAULTS, publish=False)
    assert page.evaluate("window.draft") is True


@pytest.mark.browser
def test_public_requires_explicit_mode(page):
    page.set_content('''<input type="radio" name="mode" aria-label="全員に公開">
        <button onclick="window.public=document.querySelector('input').checked">投稿する</button>''')
    submit(page, DEFAULTS, publish=True)
    assert page.evaluate("window.public") is True


@pytest.mark.browser
def test_ambiguous_selector_rejected(page):
    page.set_content('<input name="title"><input name="title">')
    with pytest.raises(RuntimeError):
        locate(page, DEFAULTS["title"])


@pytest.mark.browser
def test_fill_verify_and_tamper(page):
    page.set_content('<input name="title"><div contenteditable="true" role="textbox"></div>')
    draft = Draft(Brief("topic", event="期間：10月"), Template(), demo_copy())
    page.locator('input').fill(draft.copy.title)
    body = locate(page, DEFAULTS["body"])
    editor_html(body, render_html(draft))
    verify_editor(page, draft, {}, DEFAULTS)
    page.locator('input').fill("別のタイトル")
    with pytest.raises(RuntimeError):
        verify_editor(page, draft, {}, DEFAULTS)


@pytest.mark.browser
def test_iframe_body_fallback(page):
    page.set_content('<iframe srcdoc="<body contenteditable=\'true\'></body>"></iframe>')
    body = locate(page, DEFAULTS["body"])
    assert body is not None
    editor_html(body, "<p>こんにちは</p>")
    assert body.inner_text() == "こんにちは"


def test_public_guard_before_browser():
    with pytest.raises(ValueError):
        run_browser("default", threading.Event(), print, publish=True, allow_publish=False)


def test_cdn_origin_validation():
    assert remote_url("https://stat.ameba.jp/user_images/a.jpg")
    assert not remote_url("https://stat.ameba.jp.attacker.example/a.jpg")
    assert not remote_url("javascript:alert(1)")
