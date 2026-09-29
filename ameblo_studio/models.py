from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import json


@dataclass
class Price:
    category: str
    treatment: str
    price: str


@dataclass
class Brief:
    topic: str = ""
    event: str = ""
    notes: str = ""
    prices: list[Price] = field(default_factory=list)

    def validate(self):
        if not self.topic.strip():
            raise ValueError("주제를 입력하세요.")
        if len(self.topic) > 500 or len(self.event) > 10000 or len(self.notes) > 15000:
            raise ValueError("입력이 너무 깁니다. 주제 500자, 이벤트 10,000자, 메모 15,000자 이내로 입력하세요.")
        for row in self.prices:
            if not all(x.strip() for x in asdict(row).values()):
                raise ValueError("가격표의 카테고리·시술명·가격을 모두 입력하세요.")
        if len(self.prices) > 100:
            raise ValueError("가격표는 최대 100행입니다.")


@dataclass
class Template:
    clinic: str = "クリニック名を設定してください"
    greeting: str = "こんにちは！{clinic}です。"
    event_heading: str = "イベントのご案内"
    category_heading: str = "{emoji} {category}"
    price_line: str = "{treatment}：{price}"
    emoji: str = "🌿"
    caution: str = "施術内容・費用・リスクについては、ご予約前に当院へお問い合わせください。"
    line: str = ""
    hours: str = ""
    footer: str = "皆さまからのお問い合わせをお待ちしております。"


@dataclass
class Settings:
    provider: str = "OpenAI"
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.5-flash"
    openai_key: str = ""
    gemini_key: str = ""
    profile: str = "default"
    allow_publish: bool = False
    template: Template = field(default_factory=Template)

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        value["template"] = Template(**value.get("template", {}))
        return cls(**value)


@dataclass
class Copy:
    title: str
    intro: str
    closing: str


@dataclass
class ImagePlacement:
    path: str
    after: int = 0  # after text block number; 0 means before first block
    alt: str = ""


@dataclass
class Draft:
    brief: Brief
    template: Template
    copy: Copy
    images: list[ImagePlacement] = field(default_factory=list)

    def fingerprint(self):
        value = asdict(self)
        for item in value["images"]:
            item["sha256"] = hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, value):
        brief = dict(value["brief"])
        brief["prices"] = [Price(**r) for r in brief.get("prices", [])]
        return cls(Brief(**brief), Template(**value["template"]), Copy(**value["copy"]),
                   [ImagePlacement(**i) for i in value.get("images", [])])
