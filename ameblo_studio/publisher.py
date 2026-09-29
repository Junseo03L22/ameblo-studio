from datetime import datetime, timezone
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from filelock import FileLock, Timeout as LockTimeout
from playwright.sync_api import sync_playwright
from .content import render_html, text_blocks, validate_draft
from .models import Draft
from .selectors import EDITOR_URL, load_selectors
from .storage import data_dir, profile_dir, atomic_json, disable_password_storage


class Cancelled(RuntimeError):
    pass


def normalized(value):
    return re.sub(r"\s+", "", value)


def locate(page, candidates, *, hidden=False, frames=True):
    """Resolve a unique visible match; scoped candidates first, no arbitrary .first()."""
    for selector in candidates:
        found = []
        for scope in (page.frames if frames else [page.main_frame]):
            for node in scope.locator(selector).all():
                if hidden or node.is_visible():
                    found.append(node)
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise RuntimeError("선택자에 여러 요소가 일치합니다. selectors.json 범위를 좁혀주세요.")
    return None


def required(page, candidates, **kwargs):
    node = locate(page, candidates, **kwargs)
    if node is None:
        raise RuntimeError("필요한 편집기 요소를 찾지 못했습니다. 로그인 상태와 selectors.json을 확인하세요.")
    return node


def await_condition(page, test, stop, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop.is_set():
            raise Cancelled("작업을 취소했습니다.")
        if page.is_closed():
            raise Cancelled("브라우저가 닫혔습니다.")
        value = test()
        if value:
            return value
        page.wait_for_timeout(200)
    raise RuntimeError("화면 응답을 확인하지 못했습니다. 브라우저와 진단 파일을 확인하세요.")


def editor_html(body, html):
    body.click()
    body.evaluate("""(el, html) => {
        el.focus(); const doc = el.ownerDocument;
        const range = doc.createRange(); range.selectNodeContents(el);
        const selection = doc.defaultView.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        if (!doc.execCommand('insertHTML', false, html)) throw new Error('insertHTML unsupported');
        el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertFromPaste'}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
    }""", html)


def remote_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname == "stat.ameba.jp" or (parts.hostname or "").endswith(".stat.ameba.jp"))


def image_sources(body):
    return body.locator("img").evaluate_all("els => els.map(e => e.src)")


def upload_image(page, body, path, selectors, stop):
    # One file at a time, collecting the URL from the *inserted* image, not thumbnail URLs.
    editor_html(body, "<p><br></p>")
    file_input = locate(page, selectors["image_input"], hidden=True)
    if file_input is None:
        tab = required(page, selectors["image_tab"])
        tab.click()
        file_input = required(page, selectors["image_input"], hidden=True)
    before = set(page.locator("img").evaluate_all("els => els.map(e => e.src)"))
    file_input.set_input_files(str(Path(path).resolve()))
    clicked = False

    def insert_or_read():
        nonlocal clicked
        inserted = image_sources(body)
        if len(inserted) > 1:
            raise RuntimeError("한 파일 업로드에 여러 이미지가 삽입되었습니다. 자동화를 중단합니다.")
        if len(inserted) == 1 and remote_url(inserted[0]):
            if body.locator("img").evaluate("el => el.complete && el.naturalWidth > 0"):
                return inserted[0]
            return None
        current = page.locator("img").evaluate_all("els => els.map(e => e.src)")
        fresh = set(u for u in current if remote_url(u)) - before
        if len(fresh) == 1 and not clicked:
            url = next(iter(fresh))
            matches = [x for x in page.locator("img").all() if x.is_visible() and x.evaluate("el => el.src") == url]
            if len(matches) == 1:
                matches[0].click()
                clicked = True
        return None

    return await_condition(page, insert_or_read, stop, seconds=60)


def verify_editor(page, draft, urls, selectors):
    title = required(page, selectors["title"])
    body = required(page, selectors["body"])
    if title.input_value() != draft.copy.title:
        raise RuntimeError("브라우저 제목이 미리보기와 다릅니다. 저장을 중단합니다.")
    expected = normalized("".join(value for _, value in text_blocks(draft)))
    if normalized(body.inner_text()) != expected:
        raise RuntimeError("브라우저 본문이 미리보기와 다릅니다. 저장을 중단합니다.")
    ordered = [urls[i] for pos in range(len(text_blocks(draft)) + 1) for i, img in enumerate(draft.images) if img.after == pos]
    if image_sources(body) != ordered:
        raise RuntimeError("이미지 수 또는 순서가 일치하지 않습니다. 저장을 중단합니다.")
    # Check image *positions*, not just the order among the images. Walk text
    # nodes to record how much preceding text each image actually has.
    offsets = body.evaluate("""el => {
        let text = ''; const images = [];
        function walk(node) {
            if (node.nodeType === 3) text += node.nodeValue;
            else if (node.nodeName === 'IMG') images.push(text.replace(/\\s+/g, '').length);
            else for (const child of node.childNodes) walk(child);
        }
        walk(el); return images;
    }""")
    blocks = text_blocks(draft)
    expected_offsets = []
    for pos in range(len(blocks) + 1):
        prefix = normalized("".join(value for _, value in blocks[:pos]))
        # JavaScript string length uses UTF-16 code units (emoji count as two).
        length = len(prefix.encode("utf-16-le")) // 2
        expected_offsets.extend(length for img in draft.images if img.after == pos)
    if offsets != expected_offsets:
        raise RuntimeError("이미지의 본문 삽입 위치가 다릅니다. 저장을 중단합니다.")


def submit(page, selectors, publish):
    """No generic click is permitted until draft/public state is explicitly checked."""
    if publish:
        radio = required(page, selectors["public_radio"])
        radio.check()
        if not radio.is_checked():
            raise RuntimeError("전체 공개 옵션을 확인할 수 없습니다.")
        required(page, selectors["submit_button"]).click()
        return
    button = locate(page, selectors["draft_button"])
    if button is not None:
        button.click()
        return
    radio = required(page, selectors["draft_radio"])
    radio.check()
    if not radio.is_checked():
        raise RuntimeError("비공개 초안 옵션을 확인할 수 없습니다.")
    required(page, selectors["submit_button"]).click()


def previous_attempt(draft, profile):
    profile_dir(profile)  # Validate the profile identifier before constructing paths.
    path = data_dir() / "receipts" / f"{profile}-{draft.fingerprint()}.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def run_browser(profile, stop, log, ready=None, decision=None, *, draft: Draft | None = None,
                publish=False, allow_publish=False, retry_ack=False):
    if publish and (not allow_publish or draft is None):
        raise ValueError("공개 발행이 허용되지 않았습니다.")
    if draft:
        validate_draft(draft)
        initial_fingerprint = draft.fingerprint()
        if previous_attempt(draft, profile) and not retry_ack:
            raise ValueError("동일 초안의 이전 저장 시도가 있습니다. Ameblo에서 중복 여부를 먼저 확인하세요.")
    root = profile_dir(profile)
    stage = "browser_start"
    receipt_path = None
    submitted = False
    context = None
    page = None
    try:
        with FileLock(str(root.parent / (profile + ".lock")), timeout=0), sync_playwright() as p:
            disable_password_storage(root)
            context = p.chromium.launch_persistent_context(str(root), headless=False,
                viewport={"width": 1360, "height": 960}, locale="ja-JP",
                accept_downloads=False, args=["--disable-save-password-bubble"],
                ignore_default_args=["--password-store=basic", "--use-mock-keychain"])
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(10000)
                stage = "open_editor"
                page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=45000)
                selectors = load_selectors()
                log("브라우저에서 직접 로그인하세요. 인증·CAPTCHA는 자동 처리하지 않습니다. (최대 5분)")
                stage = "login"
                await_condition(page, lambda: locate(page, selectors["title"]), stop, seconds=300)
                if draft is None:
                    log("편집기 접근을 확인했습니다. 로그인 세션을 로컬 프로필에 저장합니다.")
                    return "로그인 세션 저장 완료"
                stage = "prepare"
                title = required(page, selectors["title"])
                body = await_condition(page, lambda: locate(page, selectors["body"]), stop)
                if title.input_value().strip() or body.inner_text().strip() or body.locator("img").count():
                    raise RuntimeError("편집기에 기존 내용이 있습니다. 새 글의 빈 편집기를 준비한 뒤 다시 시도하세요.")
                urls = {}
                for index, img in enumerate(draft.images):
                    stage = f"image_{index + 1}"
                    log(f"이미지 업로드 {index + 1}/{len(draft.images)}")
                    urls[index] = upload_image(page, body, img.path, selectors, stop)
                stage = "fill"
                title.fill(draft.copy.title)
                editor_html(body, render_html(draft, urls))
                title.click()  # blur editor so the site's state can synchronize
                await_condition(page, lambda: normalized(body.inner_text()) == normalized("".join(v for _, v in text_blocks(draft))), stop)
                verify_editor(page, draft, urls, selectors)
                stage = "review"
                if not ready or decision is None:
                    raise RuntimeError("브라우저 검수 확인 채널이 없습니다.")
                ready()
                log("브라우저의 제목·본문·이미지를 확인하고 앱에서 검수 완료를 눌러주세요.")
                await_condition(page, decision.is_set, stop, seconds=600)
                verify_editor(page, draft, urls, selectors)
                if draft.fingerprint() != initial_fingerprint:
                    raise RuntimeError("작업 중 원본 이미지 파일이 변경되었습니다. 미리보기를 다시 검수하세요.")
                if stop.is_set():
                    raise Cancelled("저장을 취소했습니다.")
                # Existing success notices must not count as the result of this attempt.
                success = selectors["public_success" if publish else "draft_success"]
                if locate(page, success):
                    raise RuntimeError("기존 완료 메시지가 남아 있어 저장 결과를 구분할 수 없습니다.")
                stage = "submit"
                receipt_path = data_dir() / "receipts" / f"{profile}-{draft.fingerprint()}.json"
                receipt = {"time": datetime.now(timezone.utc).isoformat(), "status": "unknown", "mode": "public" if publish else "draft"}
                atomic_json(receipt_path, receipt)
                submitted = True  # Set BEFORE click: timeout could mean the server accepted it.
                submit(page, selectors, publish)
                stage = "confirm_result"
                await_condition(page, lambda: locate(page, success), stop, seconds=30)
                receipt["status"] = "confirmed"
                atomic_json(receipt_path, receipt)
                return "공개 발행 완료 메시지를 확인했습니다." if publish else "임시저장 완료 메시지를 확인했습니다."
            except Exception as exc:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                folder = data_dir() / "diagnostics" / stamp
                folder.mkdir(parents=True, mode=0o700)
                if page is not None and not page.is_closed():
                    try:
                        page.screenshot(path=str(folder / "screen.png"), full_page=True, timeout=5000,
                                        mask=[page.locator('input[type="password"]')])
                    except Exception:
                        pass
                atomic_json(folder / "error.json", {"stage": stage, "exception": type(exc).__name__, "submission_may_have_happened": submitted})
                hint = "저장 여부가 불확실합니다. Ameblo 글 목록을 확인한 뒤 재시도하세요." if submitted else "저장 완료를 확인하지 못했습니다."
                raise RuntimeError(f"{exc}\n{hint}\n진단 폴더: {folder}") from None
            finally:
                context.close()
    except LockTimeout:
        raise RuntimeError("이 세션을 다른 작업/앱이 사용 중입니다. 브라우저를 닫고 다시 시도하세요.") from None
    except Exception as exc:
        if context is not None:
            raise
        folder = data_dir() / "diagnostics" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        folder.mkdir(parents=True, mode=0o700)
        atomic_json(folder / "error.json", {"stage": stage, "exception": type(exc).__name__,
                                          "submission_may_have_happened": False})
        raise RuntimeError("브라우저를 시작하지 못했습니다. Chromium 설치 및 실행 권한을 확인하세요.\n"
                           "개발 실행 시: python -m playwright install chromium\n진단 폴더: " + str(folder)) from None
