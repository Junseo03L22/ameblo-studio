"""AI writes only three prose fields. All protected facts are rendered locally."""
from html import escape
from pathlib import Path
from string import Formatter
import re
import unicodedata
from PIL import Image
from .models import Brief, Copy, Draft, Template

RISK_TERMS = ("必ず治る", "絶対安全", "副作用なし", "副作用がない", "リスクなし", "永久保証", "100%", "１００％", "完全に治る", "痛みゼロ", "業界一", "No.1", "必ず効果")


def formatted(pattern: str, values: dict, required=()) -> str:
    try:
        fields = [name for _, name, spec, conv in Formatter().parse(pattern) if name is not None]
        if any(name not in values for name in fields):
            raise ValueError("허용되지 않은 템플릿 변수")
        if any("{" + name + "}" not in pattern for name in required):
            raise ValueError("필수 템플릿 변수 누락: " + ", ".join(required))
        # No attribute access, conversions, or nested format specifications.
        if any(spec or conv for _, _, spec, conv in Formatter().parse(pattern)):
            raise ValueError("템플릿에는 단순 {변수}만 사용할 수 있습니다.")
        return pattern.format_map(values)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"템플릿 형식 오류: {exc}") from None


def validate_copy(copy: Copy, brief: Brief):
    for name, value, maximum in (("제목", copy.title, 100), ("소개", copy.intro, 2000), ("마무리", copy.closing, 1000)):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"{name}: 비어 있거나 길이 제한({maximum}자)을 초과했습니다.")
        if re.search(r"\d", unicodedata.normalize("NFKC", value)):
            raise ValueError(f"{name}에 숫자가 있습니다. 날짜·가격·수량은 고정 이벤트/가격표 영역에만 넣으세요.")
        if re.search(r"(?:円|ウォン|KRW|JPY|₩|￥|¥|税込|税抜|割引|パーセント)|[一二三四五六七八九十百千万億〇零]+(?:年|月|日|回|本|錠|倍|割)", value, re.I):
            raise ValueError(f"{name}에 금액·할인·수량 표현이 있습니다. 고정 이벤트/가격표 영역으로 옮기세요.")
        if any(x in value for x in RISK_TERMS):
            raise ValueError(f"{name}에 효과 보장 또는 과장 표현이 감지되었습니다.")
        if re.search(r"<[^>]+>", value):
            raise ValueError("AI 문구에는 HTML 태그를 넣을 수 없습니다.")
        if not re.search(r"[ぁ-んァ-ヶ一-龯]", value):
            raise ValueError(f"{name}에 일본어 문장이 필요합니다.")
    for row in brief.prices:
        if row.treatment in (copy.title + copy.intro + copy.closing):
            raise ValueError("시술명은 보호된 가격표에서만 사용하세요. AI 문구에서 시술명을 제거하세요.")


def text_blocks(draft: Draft) -> list[tuple[str, str]]:
    t, b, c = draft.template, draft.brief, draft.copy
    result = [("p", formatted(t.greeting, {"clinic": t.clinic})), ("p", c.intro)]
    if b.event:
        result += [("h2", t.event_heading), ("p", b.event)]
    categories = list(dict.fromkeys(row.category for row in b.prices))
    for category in categories:
        result.append(("h2", formatted(t.category_heading, {"emoji": t.emoji, "category": category}, ("category",))))
        for row in (r for r in b.prices if r.category == category):
            result.append(("p", formatted(t.price_line, {"treatment": row.treatment, "price": row.price}, ("treatment", "price"))))
    result.append(("p", c.closing))
    if t.caution:
        result += [("h2", "ご注意"), ("p", t.caution)]
    if t.line:
        result.append(("p", "LINE：" + t.line))
    if t.hours:
        result.append(("p", "診療時間：" + t.hours))
    if t.footer:
        result.append(("p", t.footer))
    return result


def validate_image(path: str):
    p = Path(path)
    if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif"} or not p.is_file():
        raise ValueError(f"PNG/JPG/GIF 파일이 필요합니다: {p.name}")
    if p.stat().st_size > 3 * 1024 * 1024:
        raise ValueError(f"이미지는 3MB 이하로 준비하세요: {p.name}")
    with Image.open(p) as im:
        if im.format not in {"PNG", "JPEG", "GIF"}:
            raise ValueError("실제 이미지 형식이 지원되지 않습니다.")
        im.verify()


def validate_draft(draft: Draft):
    draft.brief.validate()
    validate_copy(draft.copy, draft.brief)
    blocks = text_blocks(draft)
    if len(draft.images) > 30:
        raise ValueError("MVP에서는 이미지 최대 30장을 지원합니다.")
    for img in draft.images:
        validate_image(img.path)
        if not 0 <= img.after <= len(blocks):
            raise ValueError("이미지 삽입 위치가 본문 범위를 벗어났습니다.")
    if len(render_html(draft)) > 50000:
        raise ValueError("본문이 너무 깁니다. 50,000자 이내로 줄여주세요.")


def warnings(draft: Draft) -> list[str]:
    issues = ["가격·통화·세금·기간·시술명·효과·부작용·이미지 사용권을 직접 확인하세요. 자동 검사는 의료광고 적법성을 보장하지 않습니다.",
              "이벤트 정보·가격표·고정문구는 번역하지 않고 입력 그대로 게시됩니다. 일본어 표기를 확인하세요."]
    combined = "\n".join(value for _, value in text_blocks(draft))
    found = [x for x in RISK_TERMS if x in combined]
    if found:
        issues.append("고정문구의 과장 의심 표현: " + ", ".join(found))
    if not draft.template.line:
        issues.append("LINE 연락처가 비어 있습니다.")
    if not draft.template.hours:
        issues.append("진료시간이 비어 있습니다.")
    if "設定してください" in draft.template.clinic:
        issues.append("설정에서 실제 병원명을 입력하세요.")
    return issues


def render_html(draft: Draft, remote_images: dict[int, str] | None = None) -> str:
    blocks = text_blocks(draft)
    result = []
    for position in range(len(blocks) + 1):
        if position:
            tag, value = blocks[position - 1]
            result.append(f"<{tag}>{escape(value).replace(chr(10), '<br>')}</{tag}>")
        for index, img in enumerate(draft.images):
            if img.after == position:
                src = remote_images[index] if remote_images is not None else Path(img.path).resolve().as_uri()
                result.append(f'<p><img src="{escape(src, quote=True)}" alt="{escape(img.alt, quote=True)}" width="580"></p>')
    return "\n".join(result)


def demo_copy() -> Copy:
    return Copy("季節のイベントのご案内", "こんにちは。今月のイベント情報をご案内いたします。詳しい内容は下記をご確認ください。", "ご不明な点は、お気軽に当院までお問い合わせください。")
