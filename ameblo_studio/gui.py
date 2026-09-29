import copy
import json
import threading
from dataclasses import asdict, fields
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QLineEdit, QPlainTextEdit, QTextBrowser, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QCheckBox, QScrollArea,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QAbstractItemView, QSplitter)
from .models import Brief, Price, Copy, Draft, ImagePlacement, Settings, Template
from .storage import data_dir, load_settings, save_settings, save_draft, load_draft
from .content import demo_copy, render_html, text_blocks, validate_draft, validate_image, warnings
from .ai import generate
from .publisher import run_browser, previous_attempt
from .selectors import DEFAULTS


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    review = Signal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.stop = threading.Event()
        self.decision = threading.Event()

    def run(self):
        try:
            result = self.operation(self)
            if self.stop.is_set() and isinstance(result, Copy):
                raise RuntimeError("AI 생성 작업을 취소했습니다. 진행된 API 호출 요금은 발생할 수 있습니다.")
            self.result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle("설정 · AI / 계정 세션 / 기본 템플릿")
        self.resize(740, 790)
        self.value = copy.deepcopy(settings)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        provider_tab = QWidget()
        form = QFormLayout(provider_tab)
        self.provider = QComboBox()
        self.provider.addItems(["OpenAI", "Gemini"])
        self.provider.setCurrentText(settings.provider)
        form.addRow("AI 공급자", self.provider)
        self.entries = {}
        for name, label in [("openai_model", "OpenAI 모델"), ("gemini_model", "Gemini 모델"),
                            ("openai_key", "OpenAI API 키"), ("gemini_key", "Gemini API 키"),
                            ("profile", "Ameblo 세션 이름")]:
            entry = QLineEdit(getattr(settings, name))
            if name.endswith("key"):
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.entries[name] = entry
            form.addRow(label, entry)
        note = QLabel("환경변수 OPENAI_API_KEY / GEMINI_API_KEY가 입력값보다 우선합니다.\n"
                      "여기에 입력한 키는 이 컴퓨터의 settings.json에 평문으로 저장됩니다.\n"
                      "세션 이름을 바꾸면 별도 로그인 프로필을 사용합니다. 비밀번호는 앱이 저장하지 않습니다.\n"
                      "로그인 브라우저의 비밀번호 저장 기능은 사용하지 마세요.")
        note.setWordWrap(True)
        form.addRow(note)
        self.publish = QCheckBox("공개 발행 기능 활성화 (기본 꺼짐)")
        self.publish.setChecked(settings.allow_publish)
        form.addRow(self.publish)
        folder = QPushButton("로컬 설정 / 세션 / 로그 폴더 열기")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        form.addRow(folder)
        form.addRow(QLabel("데이터 폴더: " + str(data_dir())))
        tabs.addTab(provider_tab, "AI · 계정")
        template_page = QWidget()
        template_form = QFormLayout(template_page)
        self.template_entries = {}
        labels = {"clinic": "병원명 (일본어)", "greeting": "인사말 · {clinic}", "event_heading": "이벤트 제목",
                  "category_heading": "소제목 · {emoji} {category}", "price_line": "가격 행 · {treatment} {price}",
                  "emoji": "이모지", "caution": "주의사항", "line": "LINE 연락처 / URL", "hours": "진료시간", "footer": "고정 마무리"}
        for f in fields(Template):
            entry = QPlainTextEdit(getattr(settings.template, f.name))
            entry.setMaximumHeight(75 if f.name in {"caution", "hours", "footer"} else 52)
            self.template_entries[f.name] = entry
            template_form.addRow(labels[f.name], entry)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(template_page)
        tabs.addTab(scroll, "기본 템플릿")
        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.addWidget(QLabel("Ameblo 화면이 바뀌면 아래 선택자를 수정해 저장하세요.\n잘못된 선택자는 저장/발행 오작동을 일으킬 수 있습니다. README의 검증 절차를 확인하세요."))
        self.selector_edit = QPlainTextEdit()
        path = data_dir() / "selectors.json"
        self.selector_edit.setPlainText(path.read_text("utf-8") if path.exists() else json.dumps(DEFAULTS, ensure_ascii=False, indent=2))
        advanced_layout.addWidget(self.selector_edit)
        tabs.addTab(advanced, "고급 · DOM 선택자")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def commit(self):
        try:
            self.value.provider = self.provider.currentText()
            for key, entry in self.entries.items():
                setattr(self.value, key, entry.text().strip())
            self.value.allow_publish = self.publish.isChecked()
            self.value.template = Template(**{key: entry.toPlainText() for key, entry in self.template_entries.items()})
            sample = Draft(Brief("검증", prices=[Price("カテゴリー", "施術名", "10,000円")]), self.value.template, demo_copy())
            validate_draft(sample)
            selectors = json.loads(self.selector_edit.toPlainText())
            if not isinstance(selectors, dict) or set(selectors) != set(DEFAULTS):
                raise ValueError("선택자 키를 모두 유지하세요.")
            if any(not isinstance(v, list) or not v or any(not isinstance(s, str) or not s for s in v) for v in selectors.values()):
                raise ValueError("선택자는 비어 있지 않은 문자열 배열이어야 합니다.")
            from .storage import atomic_json
            save_settings(self.value)
            atomic_json(data_dir() / "selectors.json", selectors)
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "설정 확인", str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ameblo Studio · 일본어 포스팅 도우미")
        self.resize(1230, 900)
        self.worker = None
        self.draft = None
        self.preview_fingerprint = None
        self.load_error = None
        try:
            self.settings = load_settings()
        except Exception as exc:
            self.settings = Settings()
            self.load_error = f"기존 설정 파일을 읽지 못했습니다. 원본 파일은 유지했습니다: {exc}"
        root = QWidget()
        layout = QVBoxLayout(root)
        self.setCentralWidget(root)
        header = QHBoxLayout()
        heading = QLabel("Ameblo Studio")
        heading.setStyleSheet("font-size:26px;font-weight:700;color:#143d38")
        header.addWidget(heading)
        header.addStretch()
        self.settings_button = QPushButton("⚙ 설정")
        self.settings_button.clicked.connect(self.edit_settings)
        header.addWidget(self.settings_button)
        self.login_button = QPushButton("Ameblo 로그인 / 세션 확인")
        self.login_button.clicked.connect(self.login)
        header.addWidget(self.login_button)
        layout.addLayout(header)
        subtitle = QLabel("일본어 글 생성 → 미리보기와 검수 → Ameblo 임시저장")
        subtitle.setStyleSheet("color:#516966;font-size:14px;padding-bottom:8px")
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_input()
        self.build_preview()
        self.build_upload()
        bottom = QHBoxLayout()
        self.status = QLabel("준비됨 · 최초 실행은 설정에서 병원명과 AI 키를 입력하세요.")
        bottom.addWidget(self.status, 1)
        self.cancel = QPushButton("작업 취소")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_job)
        bottom.addWidget(self.cancel)
        layout.addLayout(bottom)
        self.setStyleSheet("""
            QMainWindow,QDialog {background:#f3f7f6;} QWidget {font-size:13px;}
            QLineEdit,QPlainTextEdit,QTextBrowser,QTableWidget {background:white;border:1px solid #c8d8d4;border-radius:5px;padding:5px;}
            QPushButton {padding:9px 14px;border-radius:6px;background:#dcebe7;color:#163e37;}
            QPushButton:hover {background:#c9e2da;} QPushButton:disabled {color:#899590;background:#e9efed;}
            QPushButton[primary="true"] {background:#176c59;color:white;font-weight:600;}
            QTabBar::tab {padding:12px 20px;} QLabel {color:#213a34;}
        """)
        if self.load_error:
            self.status.setText(self.load_error)

    def build_input(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("예: 가을 피부 관리 이벤트 안내 (한국어 가능)")
        self.event = QPlainTextEdit()
        self.event.setPlaceholderText("일본어로 입력 · 그대로 게시됩니다. 예: 期間：2026年10月1日〜10月31日\n대상·기간·세금 포함 여부 등 확정된 사실")
        self.event.setMaximumHeight(110)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("AI에 전달할 분위기/참고 메모 (환자 개인정보는 넣지 마세요)")
        self.notes.setMaximumHeight(85)
        form.addRow("주제", self.topic)
        form.addRow("이벤트 정보 (고정)", self.event)
        form.addRow("원문 메모", self.notes)
        layout.addLayout(form)
        layout.addWidget(QLabel("가격표 · 일본어 표기와 가격/통화를 직접 입력하세요. 아래 값은 AI가 변경하지 않습니다."))
        self.prices = QTableWidget(0, 3)
        self.prices.setHorizontalHeaderLabels(["카테고리 (일본어)", "시술명 (일본어)", "가격 · 통화 · 세금 표기"])
        self.prices.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prices.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.prices, 1)
        row = QHBoxLayout()
        add = QPushButton("+ 가격 행")
        add.clicked.connect(lambda: self.add_price())
        delete = QPushButton("선택 행 삭제")
        delete.clicked.connect(self.remove_prices)
        row.addWidget(add)
        row.addWidget(delete)
        row.addStretch()
        sample = QPushButton("샘플 입력")
        sample.clicked.connect(self.sample)
        row.addWidget(sample)
        layout.addLayout(row)
        actions = QHBoxLayout()
        load = QPushButton("로컬 초안 열기")
        load.clicked.connect(self.open_draft)
        actions.addWidget(load)
        demo = QPushButton("API 없이 샘플 문구로 시작")
        demo.clicked.connect(lambda: self.generate_copy(demo=True))
        actions.addWidget(demo)
        ai = QPushButton("① AI 글 생성")
        ai.setProperty("primary", True)
        ai.clicked.connect(lambda: self.generate_copy(demo=False))
        actions.addWidget(ai)
        layout.addLayout(actions)
        self.tabs.addTab(page, "① 입력 · AI 생성")
        self.topic.textChanged.connect(self.invalidate_input)
        self.event.textChanged.connect(self.invalidate_input)
        self.notes.textChanged.connect(self.invalidate_input)
        self.prices.itemChanged.connect(self.invalidate_input)

    def build_preview(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter()
        left = QWidget()
        controls = QVBoxLayout(left)
        self.title = QLineEdit()
        self.intro = QPlainTextEdit()
        self.closing = QPlainTextEdit()
        controls.addWidget(QLabel("일본어 제목 · 숫자/시술명은 고정 영역에 넣으세요"))
        controls.addWidget(self.title)
        controls.addWidget(QLabel("소개 문구"))
        controls.addWidget(self.intro)
        controls.addWidget(QLabel("마무리 문구"))
        controls.addWidget(self.closing)
        controls.addWidget(QLabel("이미지 · 같은 위치의 이미지는 표 순서대로 삽입됩니다"))
        self.images = QTableWidget(0, 3)
        self.images.setHorizontalHeaderLabels(["파일", "삽입 위치", "대체 텍스트"])
        self.images.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.images.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        controls.addWidget(self.images)
        image_actions = QHBoxLayout()
        for label, fn in [("+ 이미지", self.add_images), ("삭제", self.remove_images), ("↑", lambda: self.move_image(-1)), ("↓", lambda: self.move_image(1))]:
            button = QPushButton(label)
            button.clicked.connect(fn)
            image_actions.addWidget(button)
        controls.addLayout(image_actions)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        split.addWidget(left)
        split.addWidget(self.preview)
        split.setSizes([510, 610])
        layout.addWidget(split, 1)
        buttons = QHBoxLayout()
        refresh = QPushButton("② 미리보기 갱신 / 검증")
        refresh.setProperty("primary", True)
        refresh.clicked.connect(self.refresh_preview)
        save = QPushButton("로컬 초안 저장")
        save.clicked.connect(self.persist_draft)
        export = QPushButton("HTML + 이미지 내보내기")
        export.clicked.connect(self.export_html)
        for b in (refresh, save, export):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self.tabs.addTab(page, "② 편집 · 미리보기")
        for widget in (self.title, self.intro, self.closing):
            widget.textChanged.connect(self.invalidate_preview)
        self.images.itemChanged.connect(self.invalidate_preview)

    def build_upload(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.warning_box = QPlainTextEdit()
        self.warning_box.setReadOnly(True)
        self.warning_box.setMaximumHeight(160)
        self.warning_box.setPlainText("미리보기를 생성한 뒤 검수해주세요.")
        layout.addWidget(self.warning_box)
        self.reviewed = QCheckBox("가격·시술명·기간·의료광고 문구와 이미지 사용권을 검수했습니다.")
        layout.addWidget(self.reviewed)
        self.public = QCheckBox("이번 글을 전체 공개로 발행 (설정에서 별도 활성화 필요)")
        self.public.setEnabled(self.settings.allow_publish)
        layout.addWidget(self.public)
        layout.addWidget(QLabel("임시저장이 기본입니다. 입력 후 브라우저 검수를 한 번 더 요청합니다.\n실제 Ameblo 로그인 후 DOM 호환성은 사용 환경에서 확인이 필요합니다."))
        self.upload_button = QPushButton("③ Ameblo 임시저장 준비")
        self.upload_button.setProperty("primary", True)
        self.upload_button.clicked.connect(self.upload)
        layout.addWidget(self.upload_button)
        self.public.toggled.connect(lambda checked: self.upload_button.setText("③ Ameblo 공개 발행 준비" if checked else "③ Ameblo 임시저장 준비"))
        self.browser_confirm = QPushButton("브라우저 검수 완료 · 저장 진행")
        self.browser_confirm.setVisible(False)
        self.browser_confirm.clicked.connect(self.confirm_browser)
        layout.addWidget(self.browser_confirm)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs, 1)
        self.tabs.addTab(page, "③ 검수 · 임시저장")

    def invalidate_input(self, *_):
        if self.draft is not None:
            self.draft = None
            self.invalidate_preview()
            self.status.setText("입력이 변경되었습니다. 문구를 다시 생성해주세요.")

    def invalidate_preview(self, *_):
        self.preview_fingerprint = None
        if hasattr(self, "reviewed"):
            self.reviewed.setChecked(False)

    def read_brief(self):
        rows = []
        for r in range(self.prices.rowCount()):
            values = [(self.prices.item(r, c).text().strip() if self.prices.item(r, c) else "") for c in range(3)]
            if any(values):
                rows.append(Price(*values))
        brief = Brief(self.topic.text().strip(), self.event.toPlainText().strip(), self.notes.toPlainText().strip(), rows)
        brief.validate()
        return brief

    def add_price(self, values=None):
        r = self.prices.rowCount()
        self.prices.insertRow(r)
        for c, value in enumerate(values or ["", "", ""]):
            self.prices.setItem(r, c, QTableWidgetItem(value))
        self.invalidate_input()

    def remove_prices(self):
        for r in sorted({i.row() for i in self.prices.selectedIndexes()}, reverse=True):
            self.prices.removeRow(r)
        self.invalidate_input()

    def sample(self):
        self.topic.setText("가을 이벤트 안내")
        self.event.setPlainText("期間：2026年10月1日〜10月31日\n以下は動作確認用の架空メニューです。実際の内容に置き換えてください。")
        self.notes.setPlainText("차분하고 친근한 안내 문구. 효과를 보장하지 않기.")
        self.prices.setRowCount(0)
        self.add_price(["サンプルメニュー", "サンプル施術A", "10,000円（税込）"])

    def generate_copy(self, demo=False):
        try:
            brief = self.read_brief()
            settings = copy.deepcopy(self.settings)
            self.pending_brief = brief
            self.pending_template = settings.template
            if demo:
                self.generated(demo_copy())
                self.status.setText("샘플 문구입니다. AI 생성 결과가 아닙니다.")
            else:
                self.start_job(lambda w: generate(brief, settings), self.generated, "AI가 일본어 문구를 작성하고 있습니다…")
        except Exception as exc:
            self.error(str(exc))

    def generated(self, value):
        self.draft = Draft(self.pending_brief, self.pending_template, value)
        self.title.setText(value.title)
        self.intro.setPlainText(value.intro)
        self.closing.setPlainText(value.closing)
        self.images.setRowCount(0)
        self.refresh_preview()
        self.tabs.setCurrentIndex(1)

    def current_draft(self):
        if self.draft is None:
            raise ValueError("입력 후 AI 생성 또는 샘플 문구로 시작을 먼저 실행하세요.")
        result = copy.deepcopy(self.draft)
        result.copy = Copy(self.title.text().strip(), self.intro.toPlainText().strip(), self.closing.toPlainText().strip())
        result.images = self.read_images()
        return result

    def read_images(self):
        result = []
        for r in range(self.images.rowCount()):
            result.append(ImagePlacement(self.images.item(r, 0).data(Qt.ItemDataRole.UserRole),
                self.images.cellWidget(r, 1).currentData(), self.images.item(r, 2).text()))
        return result

    def image_row(self, item):
        if self.draft is None:
            raise ValueError("문구 생성 후 이미지를 추가하세요.")
        r = self.images.rowCount()
        self.images.insertRow(r)
        file = QTableWidgetItem(Path(item.path).name)
        file.setData(Qt.ItemDataRole.UserRole, str(Path(item.path).resolve()))
        file.setToolTip(item.path)
        file.setFlags(file.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.images.setItem(r, 0, file)
        positions = QComboBox()
        positions.addItem("글 맨 앞", 0)
        for index, (_, value) in enumerate(text_blocks(self.draft), 1):
            positions.addItem(f"{index}. {value[:22]} 뒤", index)
        positions.setCurrentIndex(min(item.after, positions.count() - 1))
        positions.currentIndexChanged.connect(self.invalidate_preview)
        self.images.setCellWidget(r, 1, positions)
        self.images.setItem(r, 2, QTableWidgetItem(item.alt))

    def add_images(self):
        if self.draft is None:
            return self.error("문구 생성 후 이미지를 추가하세요.")
        paths, _ = QFileDialog.getOpenFileNames(self, "이미지 선택 · 각 3MB 이하", "", "이미지 (*.png *.jpg *.jpeg *.gif)")
        try:
            for path in paths:
                validate_image(path)
            for path in paths:
                self.image_row(ImagePlacement(path, 2, ""))
            self.invalidate_preview()
        except Exception as exc:
            self.error(str(exc))

    def remove_images(self):
        for r in sorted({i.row() for i in self.images.selectedIndexes()}, reverse=True):
            self.images.removeRow(r)
        self.invalidate_preview()

    def move_image(self, delta):
        current = self.images.currentRow()
        target = current + delta
        if current < 0 or not 0 <= target < self.images.rowCount():
            return
        items = self.read_images()
        items[current], items[target] = items[target], items[current]
        self.images.setRowCount(0)
        for item in items:
            self.image_row(item)
        self.images.selectRow(target)
        self.invalidate_preview()

    def refresh_preview(self):
        try:
            result = self.current_draft()
            validate_draft(result)
            self.draft = result
            from html import escape
            self.preview.setHtml("<h1>" + escape(result.copy.title) + "</h1>" + render_html(result))
            self.warning_box.setPlainText("\n\n".join("• " + x for x in warnings(result)))
            self.reviewed.setChecked(False)
            self.preview_fingerprint = result.fingerprint()
            self.status.setText("미리보기 검증 완료 · ③ 탭에서 내용을 검수한 뒤 진행하세요.")
        except Exception as exc:
            self.invalidate_preview()
            self.error(str(exc))

    def persist_draft(self):
        try:
            draft = self.current_draft()
            validate_draft(draft)
            path, _ = QFileDialog.getSaveFileName(self, "로컬 초안 저장 (이미지는 원본 경로 참조)", "draft.json", "JSON (*.json)")
            if path:
                save_draft(Path(path), draft)
                self.status.setText("초안 저장 완료 · 다른 컴퓨터로 옮기면 이미지를 다시 선택하세요.")
        except Exception as exc:
            self.error(str(exc))

    def open_draft(self):
        path, _ = QFileDialog.getOpenFileName(self, "로컬 초안 열기", "", "JSON (*.json)")
        if not path:
            return
        try:
            draft = load_draft(Path(path))
            draft.brief.validate()
            self.topic.setText(draft.brief.topic)
            self.event.setPlainText(draft.brief.event)
            self.notes.setPlainText(draft.brief.notes)
            self.prices.setRowCount(0)
            for row in draft.brief.prices:
                self.add_price([row.category, row.treatment, row.price])
            self.draft = draft
            self.title.setText(draft.copy.title)
            self.intro.setPlainText(draft.copy.intro)
            self.closing.setPlainText(draft.copy.closing)
            self.images.setRowCount(0)
            for item in draft.images:
                self.image_row(item)
            self.tabs.setCurrentIndex(1)
            self.refresh_preview()
        except Exception as exc:
            self.error(str(exc))

    def export_html(self):
        try:
            draft = self.current_draft()
            validate_draft(draft)
            folder = QFileDialog.getExistingDirectory(self, "내보낼 상위 폴더 선택")
            if not folder:
                return
            from datetime import datetime
            import shutil
            from html import escape
            target = Path(folder) / ("ameblo-export-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            target.mkdir()
            (target / "images").mkdir()
            urls = {}
            for i, img in enumerate(draft.images):
                filename = f"{i + 1:02d}{Path(img.path).suffix.lower()}"
                shutil.copyfile(img.path, target / "images" / filename)
                urls[i] = "images/" + filename
            html = '<!doctype html><html lang="ja"><meta charset="utf-8"><title>' + escape(draft.copy.title) + '</title><body><h1>' + escape(draft.copy.title) + '</h1>' + render_html(draft, urls) + '</body></html>'
            (target / "index.html").write_text(html, "utf-8")
            self.status.setText("HTML 내보내기 완료: " + str(target))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        except Exception as exc:
            self.error(str(exc))

    def edit_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.value
            self.public.setChecked(False)
            self.public.setEnabled(self.settings.allow_publish)
            if self.draft:
                self.draft.template = copy.deepcopy(self.settings.template)
                items = self.read_images()
                self.images.setRowCount(0)
                for item in items:
                    self.image_row(item)
                self.invalidate_preview()
            self.status.setText("설정 저장 완료 · 템플릿 변경 후 미리보기를 갱신하세요.")

    def login(self):
        profile = self.settings.profile
        self.start_job(lambda w: run_browser(profile, w.stop, w.progress.emit), self.completed,
                       "브라우저를 여는 중입니다. 직접 로그인해주세요.")

    def upload(self):
        try:
            draft = self.current_draft()
            validate_draft(draft)
            if self.preview_fingerprint != draft.fingerprint():
                raise ValueError("내용 또는 이미지가 변경되었습니다. 미리보기를 갱신하세요.")
            if not self.reviewed.isChecked():
                raise ValueError("검수 체크박스를 먼저 선택하세요.")
            publish = self.public.isChecked()
            if publish and not self.settings.allow_publish:
                raise ValueError("설정에서 공개 발행을 활성화하세요.")
            retry_ack = False
            previous = previous_attempt(draft, self.settings.profile)
            if previous:
                answer = QMessageBox.warning(self, "중복 저장 확인", "동일 초안의 이전 시도가 있습니다 (" + previous["status"] + ").\nAmeblo 글 목록을 확인했으며 다시 저장하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                retry_ack = True
            if publish:
                answer = QMessageBox.warning(self, "전체 공개 발행", "검수한 글을 누구나 볼 수 있도록 공개합니다. 계속하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            settings = copy.deepcopy(self.settings)
            self.start_job(lambda w: run_browser(settings.profile, w.stop, w.progress.emit, w.review.emit, w.decision,
                draft=draft, publish=publish, allow_publish=settings.allow_publish, retry_ack=retry_ack), self.completed,
                "Ameblo에 내용을 입력합니다. 브라우저 검수를 기다려주세요.")
        except Exception as exc:
            self.error(str(exc))

    def start_job(self, operation, on_result, message):
        if self.worker and self.worker.isRunning():
            return
        self.worker = Worker(operation, self)
        self.worker.result.connect(on_result)
        self.worker.failed.connect(self.error)
        self.worker.progress.connect(self.log)
        self.worker.review.connect(self.ask_browser_review)
        self.worker.finished.connect(self.job_finished)
        self.tabs.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.login_button.setEnabled(False)
        self.cancel.setEnabled(True)
        self.status.setText(message)
        self.worker.start()

    def ask_browser_review(self):
        # Only the review action is enabled while the immutable snapshot is uploading.
        self.tabs.setEnabled(True)
        self.tabs.setCurrentIndex(2)
        self.tabs.setTabEnabled(0, False)
        self.tabs.setTabEnabled(1, False)
        self.upload_button.setEnabled(False)
        self.public.setEnabled(False)
        self.reviewed.setEnabled(False)
        self.browser_confirm.setVisible(True)
        self.browser_confirm.setEnabled(True)
        self.status.setText("브라우저 검수 대기 · 화면을 확인한 뒤 아래 검수 완료 버튼을 누르세요.")

    def confirm_browser(self):
        if self.worker:
            self.browser_confirm.setEnabled(False)
            self.worker.decision.set()
            self.status.setText("저장 결과를 확인하는 중입니다…")

    def cancel_job(self):
        if self.worker:
            self.worker.stop.set()
            self.status.setText("취소 요청됨 · 진행 중인 네트워크 요청이 끝나면 종료합니다.")

    def job_finished(self):
        self.tabs.setEnabled(True)
        self.tabs.setTabEnabled(0, True)
        self.tabs.setTabEnabled(1, True)
        self.upload_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.login_button.setEnabled(True)
        self.public.setEnabled(self.settings.allow_publish)
        self.reviewed.setEnabled(True)
        self.cancel.setEnabled(False)
        self.browser_confirm.setVisible(False)
        self.public.setChecked(False)

    def completed(self, text):
        self.log(text)
        self.status.setText(text)
        self.reviewed.setChecked(False)

    def log(self, text):
        self.logs.appendPlainText(text)

    def error(self, text):
        self.log(text)
        self.status.setText("작업을 완료하지 못했습니다. 안내를 확인해주세요.")
        QMessageBox.warning(self, "확인 필요", text)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel_job()
            self.status.setText("작업 취소 중입니다. 종료된 뒤 창을 닫아주세요.")
            event.ignore()
        else:
            event.accept()
