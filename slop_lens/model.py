"""Core data model for SlopLens.

A *Rule* is one measurable signal that people read as "AI slop".
Every rule carries:
  - kind      : "fingerprint" (generic / default AI output -> sameness)
                "quality"     (low-effort / hollow polish -> doesn't really work)
  - weight    : 1..5, how strongly humans react to it
  - drivers   : which human perception drivers (P1..P5) it triggers
  - why       : why a human perceives it as slop
  - fix       : concrete remedy (summary, steps, example, effort, directive)
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Dict, Any

VERSION = "0.4.0"

CATEGORIES: Dict[str, str] = {
    "visual": "시각 디자인",
    "layout": "구조·레이아웃",
    "copy": "카피·콘텐츠",
    "imagery": "이미지·에셋",
    "ux": "인터랙션·UX",
    "code": "코드 흔적",
    "game": "게임필·게임 디자인",
    "gametech": "게임 기술 완성도",
    "audio": "사운드",
    "a11y": "접근성·완성도",
}

# Five perception drivers: *why* a person feels "this is AI slop".
DRIVERS: Dict[str, Dict[str, str]] = {
    "P1": {"name": "평균 회귀", "en": "Sameness",
           "desc": "어디서 본 듯한 기본값의 조합. 수천 개의 AI 결과물과 구별되지 않는다."},
    "P2": {"name": "의도 부재", "en": "No intent",
           "desc": "이 제품·게임만의 구체적 결정이 보이지 않는다. 누구를 위해, 왜 이렇게 만들었는지 없음."},
    "P3": {"name": "껍데기 완성도", "en": "Hollow polish",
           "desc": "겉보기엔 완성품인데 눌러보면 동작하지 않거나 가짜다 (죽은 링크, 가짜 후기, alert)."},
    "P4": {"name": "언캐니 아티팩트", "en": "Uncanny artifacts",
           "desc": "생성 모델 특유의 흔적: 뭉개진 글자·손, 플라스틱 질감, 생성기 메타데이터."},
    "P5": {"name": "비일관성", "en": "Incoherence",
           "desc": "스타일·톤·규칙이 섞여 하나의 사람이 결정한 결과물로 보이지 않는다."},
}

EFFORT_COST = {"S": 1.0, "M": 2.0, "L": 3.0}
EFFORT_LABEL = {"S": "빠른 수정 (≤1시간)", "M": "핵심 개선 (반나절~1일)", "L": "깊은 리디자인 (수일)"}


@dataclass
class Evidence:
    file: str
    line: int
    snippet: str

    def to_dict(self):
        return {"file": self.file, "line": self.line, "snippet": self.snippet}


@dataclass
class Result:
    """What a detector returns. None = rule did not fire."""
    count: float
    evidence: List[Evidence] = field(default_factory=list)
    detail: str = ""
    strength: Optional[float] = None  # override computed strength (0..1)


@dataclass
class Rule:
    id: str
    title: str
    category: str
    kind: str  # fingerprint | quality
    weight: float
    drivers: List[str]
    applies: List[str]  # web / game
    why: str
    fix: Dict[str, Any]
    detect: Optional[Callable] = None
    threshold: float = 1
    saturation: float = 3
    source: str = "static"  # static | render | visual
    replaces: List[str] = field(default_factory=list)  # static rules this measured rule supersedes
    clean_supersedes: bool = True  # also drop replaced rules when the measurement came back clean

    def strength_for(self, count: float) -> float:
        if count < self.threshold:
            return 0.0
        if count >= self.saturation:
            return 1.0
        span = max(1e-9, self.saturation - self.threshold)
        return max(0.0, min(1.0, 0.4 + 0.6 * (count - self.threshold) / span))

    def to_dict(self, full=True):
        d = {
            "id": self.id, "title": self.title, "category": self.category,
            "category_label": CATEGORIES.get(self.category, self.category),
            "kind": self.kind, "weight": self.weight, "drivers": self.drivers,
            "applies": self.applies, "source": self.source,
        }
        if full:
            d.update({"why": self.why, "fix": self.fix,
                      "threshold": self.threshold, "saturation": self.saturation})
        return d


@dataclass
class Finding:
    rule: Rule
    count: float
    strength: float
    evidence: List[Evidence] = field(default_factory=list)
    detail: str = ""
    note: str = ""

    @property
    def impact(self) -> float:
        return round(self.rule.weight * self.strength, 2)

    @property
    def severity(self) -> str:
        i = self.impact
        if i >= 3.5:
            return "치명"
        if i >= 2.2:
            return "높음"
        if i >= 1.2:
            return "보통"
        return "낮음"

    def to_dict(self):
        return {
            "rule_id": self.rule.id, "title": self.rule.title,
            "category": self.rule.category,
            "category_label": CATEGORIES.get(self.rule.category, self.rule.category),
            "kind": self.rule.kind, "source": self.rule.source,
            "weight": self.rule.weight, "count": self.count,
            "strength": round(self.strength, 2), "impact": self.impact,
            "severity": self.severity, "drivers": self.rule.drivers,
            "detail": self.detail, "note": self.note,
            "evidence": [e.to_dict() for e in self.evidence],
            "why": self.rule.why, "fix": self.rule.fix,
        }


class _Clean:
    """Returned by a render rule that was evaluated and found no problem."""
    def __repr__(self):
        return "CLEAN"


CLEAN = _Clean()

RULES: List[Rule] = []


def rule(**kw):
    """Decorator: register a detector function as a Rule."""
    def deco(fn):
        RULES.append(Rule(detect=fn, **kw))
        return fn
    return deco
