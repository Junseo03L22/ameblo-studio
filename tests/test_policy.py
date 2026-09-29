"""Policy regression tests that do not require a browser process."""
import json
import threading
import urllib.error
from unittest.mock import Mock
import pytest
from ameblo_studio import publisher, ai
from ameblo_studio.models import Draft, Brief, Template
from ameblo_studio.content import demo_copy
from ameblo_studio.selectors import DEFAULTS
from ameblo_studio.storage import atomic_json


def test_default_action_only_uses_draft_control(monkeypatch):
    draft_button = Mock()
    public_button = Mock()
    def locate(page, selectors, **kwargs):
        return draft_button if selectors == DEFAULTS['draft_button'] else public_button
    monkeypatch.setattr(publisher, 'locate', locate)
    publisher.submit(Mock(), DEFAULTS, publish=False)
    draft_button.click.assert_called_once()
    public_button.click.assert_not_called()


def test_missing_draft_control_cannot_fall_through_to_public(monkeypatch):
    submit_button = Mock()
    def locate(page, selectors, **kwargs):
        return submit_button if selectors == DEFAULTS['submit_button'] else None
    monkeypatch.setattr(publisher, 'locate', locate)
    with pytest.raises(RuntimeError):
        publisher.submit(Mock(), DEFAULTS, publish=False)
    submit_button.click.assert_not_called()


def test_unchecked_draft_mode_stops_submission(monkeypatch):
    radio = Mock()
    radio.is_checked.return_value = False
    button = Mock()
    def locate(page, selectors, **kwargs):
        if selectors == DEFAULTS['draft_button']:
            return None
        return radio if selectors == DEFAULTS['draft_radio'] else button
    monkeypatch.setattr(publisher, 'locate', locate)
    with pytest.raises(RuntimeError):
        publisher.submit(Mock(), DEFAULTS, publish=False)
    button.click.assert_not_called()


def test_duplicate_unknown_attempt_blocks_before_launch(tmp_path, monkeypatch):
    monkeypatch.setenv('AMEBLO_STUDIO_HOME', str(tmp_path))
    draft = Draft(Brief('topic'), Template(), demo_copy())
    atomic_json(tmp_path / 'receipts' / f'default-{draft.fingerprint()}.json', {'status': 'unknown'})
    launch = Mock()
    monkeypatch.setattr(publisher, 'sync_playwright', launch)
    with pytest.raises(ValueError, match='이전 저장 시도'):
        publisher.run_browser('default', threading.Event(), print, draft=draft)
    launch.assert_not_called()


def test_cancel_prevents_wait_test_and_further_work():
    stop = threading.Event()
    stop.set()
    work = Mock()
    with pytest.raises(publisher.Cancelled):
        publisher.await_condition(Mock(), work, stop)
    work.assert_not_called()


def test_api_http_errors_do_not_leak_server_body(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError('https://example.com', 401, 'secret-key-and-private-content', {}, None)
    monkeypatch.setattr(ai.urllib.request, 'urlopen', fail)
    with pytest.raises(RuntimeError) as exc:
        ai.post_json('https://example.com', {}, {})
    assert 'secret-key' not in str(exc.value)
    assert '401' in str(exc.value)


def test_browser_start_failure_writes_diagnostic(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setenv('AMEBLO_STUDIO_HOME', str(tmp_path))
    manager = MagicMock()
    manager.__enter__.return_value.chromium.launch_persistent_context.side_effect = RuntimeError('launch denied')
    monkeypatch.setattr(publisher, 'sync_playwright', lambda: manager)
    with pytest.raises(RuntimeError, match='브라우저를 시작하지 못했습니다'):
        publisher.run_browser('default', threading.Event(), lambda _: None)
    paths = list((tmp_path / 'diagnostics').glob('*/error.json'))
    assert len(paths) == 1
    record = json.loads(paths[0].read_text())
    assert record['stage'] == 'browser_start'
    assert record['submission_may_have_happened'] is False
