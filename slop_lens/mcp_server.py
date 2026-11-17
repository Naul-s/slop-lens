"""Zero-dependency MCP server (JSON-RPC 2.0 over stdio, newline-delimited).

Works with any MCP client: Claude Code, Codex CLI, Gemini CLI, Cursor, VS Code Copilot,
Windsurf, Cline, Zed, Goose… Run:  python -m slop_lens.mcp_server
"""
import io
import json
import os
import sys
import traceback

from . import report
from .engine import scan
from .model import CATEGORIES, VERSION
from .rubric import rubric_markdown
from .rules import find_rule, get_rules

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
_SCANS = {}

TOOLS = [
    {
        "name": "slop_scan",
        "title": "AI Slop 판독 (정적 분석)",
        "description": "AI로 만든 웹사이트/게임(로컬 폴더·파일 또는 http(s) URL)을 정적 기준 61개 + (Node 설치 시) 실제 브라우저 렌더 측정 25개로 분석해 Slop Index(0-100), "
                       "AI 지문/완성도 결함 2축, 영역별 점수, 근거(file:line), 사람이 슬롭으로 느끼는 이유, 구체적 해결책과 수정 계획을 반환합니다. "
                       "결과의 scan_id로 시각 검토 제출·수정 계획 조회가 가능합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "검사할 폴더/파일의 절대 경로 또는 http(s) URL"},
                "kind": {"type": "string", "enum": ["auto", "web", "game"], "default": "auto"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                "max_findings": {"type": "integer", "default": 15, "minimum": 1, "maximum": 80},
                "html_report_path": {"type": "string", "description": "지정하면 HTML 리포트를 이 경로에 저장"},
                "perception": {"type": "string", "enum": ["auto", "off"], "default": "auto",
                               "description": "에셋·사운드·프레임 지각 분석과 리뷰용 시트 생성 (Node 필요)"},
                "render": {"type": "string", "enum": ["auto", "on", "off"], "default": "auto",
                           "description": "auto: Node 렌더 프로브가 설치돼 있으면 실제 브라우저로 렌더링·클릭·플레이해 측정 (15~60초). off: 정적 분석만"},
                "screenshots_dir": {"type": "string", "description": "스크린샷 저장 폴더 (기본: 시스템 임시 폴더)"},
                "reveal": {"type": "boolean", "default": False,
                           "description": "게임은 기본적으로 리뷰 제출 전까지 측정 결과를 숨깁니다(블라인드). true면 바로 공개하고, 이후 리뷰는 블라인드가 아닌 것으로 기록"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "slop_review_protocol",
        "title": "지각 리뷰 프로토콜 (판정의 핵심)",
        "description": "slop_scan 결과를 바탕으로, 리뷰어(이미지를 볼 수 있는 에이전트 또는 사람)가 직접 봐야 할 화면 시트·플레이 프레임·에셋 시트 경로와 "
                       "사운드 분석 요약, 감각별(S1 첫인상 ~ S8 실체, C1 공들인 흔적) 답변 형식을 돌려줍니다. 시트 이미지를 실제로 열어 보고 답하세요. "
                       "AI 슬롭인지는 보이고 들리는 것으로 판단합니다.",
        "inputSchema": {"type": "object", "properties": {"scan_id": {"type": "string"},
            "blind": {"type": "boolean", "default": False, "description": "true면 측정 결과를 숨긴 블라인드 프로토콜 (리뷰가 측정에 끌려가지 않게)"},
            "attach": {"type": "array", "items": {"type": "string"},
                       "description": "직접 찍은 스크린샷 경로 (자동 캡처가 못 본 화면). 원본 확인 목록에 추가됨"}},
            "required": ["scan_id"]},
    },
    {
        "name": "slop_submit_review",
        "title": "지각 리뷰 제출 → 판정 확정",
        "description": "감각별 레벨(0 공들임 ~ 4 명백한 슬롭), 근거(어느 시트/프레임/에셋의 어디), 왜 그렇게 느껴지는지, 해결책을 제출하면 "
                       "리뷰 65% + 측정 근거 35%로 판정을 확정하고 '왜 AI 슬롭으로 느껴지나' 섹션을 리뷰 내용으로 채웁니다.",
        "inputSchema": {"type": "object", "properties": {
            "scan_id": {"type": "string"},
            "review": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string", "enum": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "C1"]},
                "level": {"type": ["integer", "string"], "description": "0~4 또는 na"},
                "evidence": {"type": "string"}, "why": {"type": "string"}, "fix": {"type": "string"}}, "required": ["id", "level"]}},
            "frames": {"type": "array", "description": "프레임별 원본 확인 메모 [{file, note}]", "items": {"type": "object", "properties": {
                "file": {"type": "string"}, "note": {"type": "string"}}, "required": ["file", "note"]}},
            "attach": {"type": "array", "items": {"type": "string"},
                       "description": "리뷰에 쓴, 직접 찍은 스크린샷 경로. frames 메모의 file에 절대 경로를 써도 자동 첨부됨"},
            "meta": {"type": "object", "description": "{reviewer, blind: 측정을 안 보고 리뷰했나, knew_expected: 기대 판정을 미리 알았나} → 신뢰도에 반영",
                     "properties": {"reviewer": {"type": "string"}, "blind": {"type": "boolean"}, "knew_expected": {"type": "boolean"}}},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}},
            "required": ["scan_id", "review"]},
    },
    {
        "name": "slop_visual_rubric",
        "title": "시각 검토 루브릭",
        "description": "스크린샷을 볼 수 있는 에이전트가 직접 판정할 '사람의 눈' 체크리스트(웹 15항목 / 게임 16항목)와 제출 템플릿을 반환합니다. "
                       "scan_id를 주면 렌더 프로브가 찍어 둔 스크린샷 경로(데스크톱·모바일·게임 플레이)도 알려주므로 그 이미지를 열어 보고 답하세요.",
        "inputSchema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["web", "game"], "default": "web"},
            "scan_id": {"type": "string"}}},
    },
    {
        "name": "slop_submit_visual_review",
        "title": "시각 검토 제출",
        "description": "slop_visual_rubric 항목에 대한 판정(yes=슬롭 있음/partial/no/na)을 제출하면 정적 점수와 합산해 최종 판정·신뢰도·수정 계획을 갱신합니다.",
        "inputSchema": {"type": "object", "properties": {
            "scan_id": {"type": "string"},
            "answers": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "answer": {"type": "string", "enum": ["yes", "partial", "no", "na"]},
                "note": {"type": "string"}}, "required": ["id", "answer"]}},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}},
            "required": ["scan_id", "answers"]},
    },
    {
        "name": "slop_fix_plan",
        "title": "수정 계획 + Anti-Slop 브리프",
        "description": "scan_id의 발견 사항을 노력 대비 영향 순으로 정렬한 단계별 수정 계획, 단계별 예상 점수, 그리고 코딩 에이전트에 붙여넣을 수 있는 리디자인 브리프를 반환합니다.",
        "inputSchema": {"type": "object", "properties": {
            "scan_id": {"type": "string"}, "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            "reveal": {"type": "boolean", "default": False, "description": "리뷰 전인 게임의 수정 계획을 지금 공개 (이후 리뷰는 블라인드 아님)"}},
            "required": ["scan_id"]},
    },
    {
        "name": "slop_explain_rule",
        "title": "판정 기준 설명",
        "description": "규칙 ID(예: VIS-01, CPY-03, GAM-04, VR-03)의 판정 기준, 사람이 슬롭으로 느끼는 이유, 해결 방법과 예시를 반환합니다.",
        "inputSchema": {"type": "object", "properties": {"rule_id": {"type": "string"}}, "required": ["rule_id"]},
    },
    {
        "name": "slop_list_rules",
        "title": "판정 기준 목록",
        "description": "SlopLens의 모든 판정 기준을 영역별로 나열합니다.",
        "inputSchema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["web", "game"]},
            "category": {"type": "string", "enum": list(CATEGORIES.keys())}}},
    },
]

PROMPTS = [
    {"name": "slop_audit", "title": "AI Slop 전체 감사",
     "description": "정적 분석 → 시각 검토 → 최종 판정 → 수정 계획까지 전체 워크플로를 실행합니다.",
     "arguments": [{"name": "target", "description": "폴더 경로 또는 URL", "required": True}]},
    {"name": "slop_fix", "title": "AI Slop 수정 실행",
     "description": "가장 최근 검사 결과의 수정 계획을 빠른 수정부터 실제로 적용합니다.",
     "arguments": [{"name": "target", "description": "폴더 경로", "required": True}]},
]


def _audit_prompt(target):
    return (f"SlopLens로 `{target}`의 AI 슬롭 여부를 판독해줘.\n\n"
            "1. `slop_scan`(target 지정)으로 정적 분석을 실행한다.\n"
            "2. 화면을 볼 수 있다면(브라우저/스크린샷 도구) 데스크톱 1440px·모바일 390px 스크린샷을 찍고, 게임이면 30초 플레이한다. "
            "`slop_visual_rubric`을 받아 각 항목을 yes/partial/no/na로 판정하고 근거를 적어 `slop_submit_visual_review`로 제출한다. "
            "화면을 볼 수 없다면 이 단계를 건너뛰고 그 사실을 보고한다.\n"
            "3. 최종 판정을 사용자에게 설명한다: Slop Index, 유형(2축), 가장 큰 원인 3가지(근거 file:line 포함), 사람이 그렇게 느끼는 이유.\n"
            "4. `slop_fix_plan`으로 단계별 수정 계획과 Anti-Slop 브리프를 제시하고, 바로 적용할지 묻는다.")


def _fix_prompt(target):
    return (f"`{target}`에 SlopLens 수정 계획을 적용해줘.\n\n"
            "1. `slop_scan`으로 현재 상태를 검사한다.\n2. `slop_fix_plan`의 '빠른 수정' 항목부터 근거 위치(file:line)를 열어 실제로 수정한다. "
            "가짜 데이터는 지어내지 말고, 실제 정보가 필요한 곳(후기·통계·연락처)은 삭제하거나 TODO 목록으로 사용자에게 묻는다.\n"
            "3. 핵심 개선 항목은 Anti-Slop 브리프의 '먼저 결정할 것' 질문에 대한 답을 사용자에게 받은 뒤 진행한다.\n"
            "4. 수정 후 `slop_scan`을 다시 실행해 전후 점수를 비교 보고한다.")


def _text(s, is_error=False):
    return {"content": [{"type": "text", "text": s}], "isError": is_error}


def _get_scan(scan_id):
    r = _SCANS.get(scan_id)
    if not r:
        raise ValueError(f"scan_id '{scan_id}'를 찾을 수 없습니다. 먼저 slop_scan을 실행하세요 (서버 재시작 시 초기화됨).")
    return r


def _plan_markdown(res):
    plan = res.fix_plan()
    L = [f"# 수정 계획 — 현재 Slop Index {res.index:.0f}", ""]
    for ph, pj in zip(plan["phases"], plan["projections"]):
        if not ph["items"]:
            continue
        L.append(f"## {ph['label']} → 완료 시 예상 {pj['index']:.0f}")
        for it in ph["items"]:
            L.append(f"### [{it['rule_id']}] {it['title']} ({it['severity']}, 우선순위 {it['priority']})")
            L.append(it["summary"])
            for i, s in enumerate(it["steps"], 1):
                L.append(f"{i}. {s}")
            if it["where"]:
                L.append("위치: " + ", ".join(f"`{w}`" for w in it["where"]))
            if it["example"]:
                L.append("```\n" + it["example"] + "\n```")
            L.append("")
    L += ["---", "", plan["brief"]]
    return "\n".join(L)


def call_tool(name, args):
    if name == "slop_scan":
        target = args.get("target", "")
        if not target:
            return _text("target이 필요합니다.", True)
        res = scan(target, args.get("kind", "auto"), args.get("render", "auto"), args.get("screenshots_dir"), args.get("perception", "auto"))
        _SCANS[res.id] = res
        if args.get("html_report_path"):
            p = os.path.abspath(args["html_report_path"])
            with open(p, "w", encoding="utf-8") as f:
                f.write(report.to_html(res))
        mf = int(args.get("max_findings", 15))
        if report.needs_blind(res) and not args.get("reveal"):
            return _text(report.blind_summary(res, as_json=args.get("format") == "json"))
        res.revealed = True
        if args.get("format") == "json":
            return _text(report.to_json(res, mf))
        return _text(report.to_markdown(res, max_findings=mf))
    if name == "slop_review_protocol":
        from .review import protocol_markdown
        return _text(protocol_markdown(_get_scan(args.get("scan_id", "")), blind=bool(args.get("blind")), attach=args.get("attach")))
    if name == "slop_submit_review":
        res = _get_scan(args.get("scan_id", ""))
        unknown = res.add_review(args.get("review") or [], args.get("frames"), args.get("meta"), attach=args.get("attach"))
        body = report.to_json(res) if args.get("format") == "json" else report.to_markdown(res, max_findings=15)
        if unknown:
            body = f"> 알 수 없는 항목 ID 무시: {', '.join(unknown)}\n\n" + body
        return _text(body)
    if name == "slop_visual_rubric":
        kind = args.get("kind") or "web"
        sid = args.get("scan_id", "")
        shots = None
        if sid in _SCANS:
            kind = _SCANS[sid].kind
            rr = _SCANS[sid].ctx.render
            shots = rr.get("screenshots") if rr and rr.get("ok") else None
        return _text(rubric_markdown(kind, sid, shots))
    if name == "slop_submit_visual_review":
        res = _get_scan(args.get("scan_id", ""))
        unknown = res.add_visual_answers(args.get("answers") or [])
        body = report.to_json(res) if args.get("format") == "json" else report.to_markdown(res, max_findings=15)
        if unknown:
            body = f"> 알 수 없는 항목 ID 무시: {', '.join(unknown)}\n\n" + body
        return _text(body)
    if name == "slop_fix_plan":
        res = _get_scan(args.get("scan_id", ""))
        if report.needs_blind(res) and not args.get("reveal"):
            return _text("이 게임은 아직 지각 리뷰 전이라 수정 계획(=측정 결과)을 숨기고 있습니다. "
                         f"slop_review_protocol {{scan_id: \"{res.id}\", blind: true}} → slop_submit_review 후에 다시 요청하거나, "
                         "지금 보려면 reveal: true를 주세요 (이후 리뷰는 블라인드가 아닌 것으로 기록).")
        res.revealed = True
        if args.get("format") == "json":
            return _text(json.dumps(res.fix_plan(), ensure_ascii=False, indent=2))
        return _text(_plan_markdown(res))
    if name == "slop_explain_rule":
        r = find_rule(args.get("rule_id", ""))
        if not r:
            return _text("해당 규칙이 없습니다. slop_list_rules로 목록을 확인하세요.", True)
        return _text(explain_markdown(r))
    if name == "slop_list_rules":
        rs = get_rules(args.get("kind"), args.get("category"))
        L = []
        for cat, label in CATEGORIES.items():
            sub = [r for r in rs if r.category == cat]
            if sub:
                L.append(f"## {label} ({cat})")
                L += [f"- **{r.id}** {r.title} — 가중치 {r.weight}, {'AI 지문' if r.kind == 'fingerprint' else '완성도 결함'}, {'/'.join(r.applies)}" for r in sub]
        L.append("\n시각 검토 항목(VR-xx/VG-xx)은 slop_visual_rubric으로 확인하세요.")
        return _text("\n".join(L))
    return _text(f"알 수 없는 도구: {name}", True)


def explain_markdown(r):
    fx = r.fix
    L = [f"# [{r.id}] {r.title}", "",
         f"- 영역: {CATEGORIES.get(r.category, r.category)} · 유형: {'AI 지문' if r.kind == 'fingerprint' else '완성도 결함'} · 가중치 {r.weight}/5 · "
         f"지각 요인: {', '.join(r.drivers)} · 적용: {'/'.join(r.applies)} · 출처: {'시각 검토' if r.source == 'visual' else '정적 분석'}",
         f"- 발동 기준: {r.threshold:g}회 이상, {r.saturation:g}회에서 최대 강도" if r.source == "static" else "- 발동 기준: 검토자가 yes/partial로 판정",
         "", "## 왜 사람이 슬롭으로 느끼나", r.why, "", "## 해결", fx.get("summary", "")]
    L += [f"{i}. {s}" for i, s in enumerate(fx.get("steps", []), 1)]
    if fx.get("example"):
        L += ["", "```", fx["example"], "```"]
    if fx.get("directive"):
        L += ["", f"> 에이전트 지시문: {fx['directive']}"]
    return "\n".join(L)


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params") or {}
    if mid is None:  # notification
        return None
    try:
        if method == "initialize":
            req = params.get("protocolVersion")
            ver = req if req in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            result = {"protocolVersion": ver,
                      "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                      "serverInfo": {"name": "slop-lens", "title": "SlopLens — AI Slop Detector", "version": VERSION},
                      "instructions": "AI가 만든 웹사이트/게임이 왜 AI 슬롭으로 느껴지는지 판독합니다. slop_scan → slop_review_protocol(시트 이미지를 직접 보고) → "
                                      "slop_submit_review → slop_fix_plan 순서로 사용하세요. Unity 게임은 먼저 CLI `slop-lens unity-capture`로 실행 캡처를 만들면 화면·사운드까지 판독합니다. 결과는 한국어로 설명합니다."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                result = call_tool(params.get("name"), params.get("arguments") or {})
            except Exception as e:
                result = _text(f"오류: {e.__class__.__name__}: {e}", True)
        elif method == "prompts/list":
            result = {"prompts": PROMPTS}
        elif method == "prompts/get":
            name = params.get("name")
            target = (params.get("arguments") or {}).get("target", ".")
            text = _audit_prompt(target) if name == "slop_audit" else _fix_prompt(target) if name == "slop_fix" else None
            if text is None:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown prompt {name}"}}
            result = {"description": name, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
        elif method in ("resources/list",):
            result = {"resources": []}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e), "data": traceback.format_exc()[-800:]}}


def serve():
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            stdout.flush()
            continue
        batch = msg if isinstance(msg, list) else [msg]
        replies = [r for r in (handle(m) for m in batch) if r is not None]
        for r in replies:
            stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
        stdout.flush()


if __name__ == "__main__":
    serve()
