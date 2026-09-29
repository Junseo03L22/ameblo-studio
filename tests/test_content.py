import pytest
from PIL import Image
from ameblo_studio.models import Brief, Price, Draft, Template, Copy, ImagePlacement
from ameblo_studio.content import demo_copy, render_html, validate_draft, validate_copy, formatted, text_blocks
from ameblo_studio.storage import save_draft, load_draft, Settings, save_settings, load_settings, api_key, profile_dir


@pytest.fixture
def draft():
    return Draft(Brief("가을 안내", "期間：10月1日〜31日", prices=[Price("肌管理", "施術A", "99,000ウォン（税込）")]), Template(), demo_copy())


def test_protected_facts_are_exact(draft):
    validate_draft(draft)
    html = render_html(draft)
    assert "施術A：99,000ウォン（税込）" in html
    assert "期間：10月1日〜31日" in html


@pytest.mark.parametrize("value", ["期間は１０月です", "価格は990円です", "必ず治る施術です", "施術Aのご案内です", "<script>こんにちは</script>"])
def test_unsafe_ai_copy_blocked(draft, value):
    draft.copy.intro = value
    with pytest.raises(ValueError):
        validate_copy(draft.copy, draft.brief)


def test_escape_user_html(draft):
    draft.brief.event = '<script>alert("bad")</script>'
    assert "<script>" not in render_html(draft)
    assert "&lt;script&gt;" in render_html(draft)


def test_required_template_fields(draft):
    draft.template.price_line = "{treatment}：特別価格"
    with pytest.raises(ValueError):
        validate_draft(draft)
    with pytest.raises(ValueError):
        formatted("{clinic.__class__}", {"clinic": "test"})


def test_image_positions_and_order(draft, tmp_path):
    paths = [tmp_path / f"{i}.png" for i in range(3)]
    for p in paths:
        Image.new("RGB", (10, 10)).save(p)
    draft.images = [ImagePlacement(str(paths[0]), 2), ImagePlacement(str(paths[1]), 0), ImagePlacement(str(paths[2]), 2)]
    validate_draft(draft)
    html = render_html(draft, {0: "A", 1: "B", 2: "C"})
    assert html.index('src="B"') < html.index(draft.copy.intro) < html.index('src="A"') < html.index('src="C"')
    original = draft.fingerprint()
    Image.new("RGB", (11, 10)).save(paths[0])
    assert draft.fingerprint() != original


def test_invalid_image_position(draft, tmp_path):
    image = tmp_path / "a.png"
    Image.new("RGB", (2, 2)).save(image)
    draft.images = [ImagePlacement(str(image), len(text_blocks(draft)) + 1)]
    with pytest.raises(ValueError):
        validate_draft(draft)


def test_settings_draft_roundtrip_and_key_precedence(draft, tmp_path, monkeypatch):
    monkeypatch.setenv("AMEBLO_STUDIO_HOME", str(tmp_path / "data"))
    settings = Settings(openai_key="local-test-key")
    save_settings(settings)
    assert load_settings().openai_key == "local-test-key"
    monkeypatch.setenv("OPENAI_API_KEY", "environment-test-key")
    assert api_key(settings) == "environment-test-key"
    path = tmp_path / "draft.json"
    save_draft(path, draft)
    assert load_draft(path) == draft
    assert "local-test-key" not in path.read_text()
    with pytest.raises(ValueError):
        profile_dir("../../outside")


@pytest.mark.parametrize('value', ['価格は二万円です。', '三回の施術です。', '割引のご案内です。'])
def test_kanji_price_and_quantity_blocked(draft, value):
    draft.copy.intro = value
    with pytest.raises(ValueError):
        validate_copy(draft.copy, draft.brief)


def test_browser_password_saving_disabled(tmp_path):
    import json
    from ameblo_studio.storage import disable_password_storage, atomic_json
    path = tmp_path / 'Default' / 'Preferences'
    atomic_json(path, {'unrelated': {'keep': True}, 'profile': {'name': 'Local'}})
    disable_password_storage(tmp_path)
    value = json.loads(path.read_text())
    assert value['unrelated']['keep'] is True
    assert value['profile']['name'] == 'Local'
    assert value['profile']['password_manager_enabled'] is False
    assert value['credentials_enable_service'] is False
