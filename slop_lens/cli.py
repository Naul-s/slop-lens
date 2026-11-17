"""SlopLens CLI — usable by humans, CI, and agents without MCP support.

  slop-lens scan <path|url> [--kind auto|web|game] [--format md|json|html] [--out FILE]
                            [--visual answers.json] [--fail-over N]
  slop-lens rubric [--kind web|game]
  slop-lens rules [--kind web|game] [--category visual|...]
  slop-lens explain <RULE_ID>
  slop-lens brief <path|url>         # paste-ready anti-slop redesign brief
  slop-lens mcp                      # start MCP stdio server
"""
import argparse
import json
import sys

from . import report
from .engine import scan
from .model import CATEGORIES, VERSION
from .rubric import rubric_markdown
from .rules import find_rule, get_rules


def _out(text, path=None):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"저장됨: {path}", file=sys.stderr)
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(text)


def main(argv=None):
    p = argparse.ArgumentParser(prog="slop-lens", description="AI Slop 판독기 — AI로 만든 웹사이트/게임 분석")
    p.add_argument("--version", action="version", version=f"SlopLens {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="폴더/파일/URL 검사")
    s.add_argument("target")
    s.add_argument("--kind", default="auto", choices=["auto", "web", "game"])
    s.add_argument("--format", default="md", choices=["md", "json", "html"])
    s.add_argument("--out")
    s.add_argument("--max-findings", type=int, default=20)
    s.add_argument("--visual", help="시각 검토 답변 JSON 파일 ({answers:[{id,answer,note}]})")
    s.add_argument("--fail-over", type=float, help="Slop Index가 이 값을 넘으면 종료 코드 1 (CI용)")
    s.add_argument("--render", default="auto", choices=["auto", "on", "off"], help="실제 브라우저 렌더 측정 (Node 프로브 필요)")
    s.add_argument("--shots", help="스크린샷 저장 폴더")
    s.add_argument("--review", help="지각 리뷰 JSON ({review:[{id,level,evidence,why,fix}]}) → 판정 확정")
    s.add_argument("--perception", default="auto", choices=["auto", "off"])
    s.add_argument("--protocol", action="store_true", help="판정 대신 지각 리뷰 프로토콜(볼 자료·답변 형식) 출력")
    s.add_argument("--blind", action="store_true", help="--protocol과 함께: 측정 결과를 숨긴 블라인드 리뷰 프로토콜")

    b = sub.add_parser("brief", help="Anti-Slop 리디자인 브리프만 출력")
    b.add_argument("target")
    b.add_argument("--kind", default="auto", choices=["auto", "web", "game"])
    b.add_argument("--out")
    b.add_argument("--render", default="auto", choices=["auto", "on", "off"])

    r = sub.add_parser("rubric", help="시각 검토 루브릭 출력")
    r.add_argument("--kind", default="web", choices=["web", "game"])

    l = sub.add_parser("rules", help="판정 기준 목록")
    l.add_argument("--kind", choices=["web", "game"])
    l.add_argument("--category", choices=list(CATEGORIES.keys()))
    l.add_argument("--json", action="store_true")

    e = sub.add_parser("explain", help="규칙 상세 설명")
    e.add_argument("rule_id")

    sub.add_parser("mcp", help="MCP stdio 서버 실행")
    sub.add_parser("doctor", help="렌더 프로브(Node·Playwright·브라우저) 설치 상태 확인")
    u = sub.add_parser("unity-capture", help="Unity 프로젝트를 복사본에서 빌드·자동 플레이해 화면·사운드 수집 (원본 무수정)")
    u.add_argument("project")
    u.add_argument("--seconds", type=int, default=30)

    a = p.parse_args(argv)

    if a.cmd == "mcp":
        from .mcp_server import serve
        serve()
        return 0
    if a.cmd == "unity-capture":
        from . import unity as _u
        try:
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        except Exception:
            pass
        res = _u.capture(a.project, a.seconds, log=lambda m: print(m, flush=True))
        print(json.dumps({k: res.get(k) for k in ("ok", "error", "editor", "editor_match", "out", "elapsed_s", "frames", "mixWav", "fmod", "log", "log_errors")},
                         ensure_ascii=False, indent=1))
        return 0 if res.get("ok") else 1
    if a.cmd == "doctor":
        from . import render as _r
        st = _r.status()
        print(f"Python     : {sys.version.split()[0]} (정적 분석 사용 가능)")
        print(f"Node       : {_r.find_node() or '없음'}")
        print("렌더 프로브: " + ("사용 가능" if st["available"] else "사용 불가 — " + st["reason"]))
        return 0
    if a.cmd == "scan":
        res = scan(a.target, a.kind, a.render, a.shots, a.perception)
        if a.protocol:
            from .review import protocol_markdown
            _out(protocol_markdown(res, blind=a.blind), a.out)
            return 0
        if a.review:
            with open(a.review, encoding="utf-8") as f:
                rv = json.load(f)
            unknown = res.add_review(rv.get("review", rv if isinstance(rv, list) else []), rv.get("frames") if isinstance(rv, dict) else None,
                                   rv.get("meta") if isinstance(rv, dict) else None)
            if unknown:
                print("알 수 없는 리뷰 ID 무시: " + ", ".join(unknown), file=sys.stderr)
        if a.visual:
            with open(a.visual, encoding="utf-8") as f:
                data = json.load(f)
            unknown = res.add_visual_answers(data.get("answers", data if isinstance(data, list) else []))
            if unknown:
                print("알 수 없는 루브릭 ID 무시: " + ", ".join(unknown), file=sys.stderr)
        if a.format == "json":
            _out(report.to_json(res), a.out)
        elif a.format == "html":
            _out(report.to_html(res), a.out)
        else:
            _out(report.to_markdown(res, max_findings=a.max_findings), a.out)
        if a.fail_over is not None and res.index > a.fail_over:
            print(f"Slop Index {res.index:.0f} > {a.fail_over:g} → 실패", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "brief":
        res = scan(a.target, a.kind, a.render)
        _out(res.brief(), a.out)
        return 0
    if a.cmd == "rubric":
        _out(rubric_markdown(a.kind))
        return 0
    if a.cmd == "rules":
        rs = get_rules(a.kind, a.category)
        if a.json:
            _out(json.dumps([x.to_dict() for x in rs], ensure_ascii=False, indent=2))
        else:
            lines = []
            for cat, label in CATEGORIES.items():
                sub_r = [x for x in rs if x.category == cat]
                if sub_r:
                    lines.append(f"\n[{label}]")
                    lines += [f"  {x.id:8} w{x.weight:<3g} {'지문' if x.kind == 'fingerprint' else '결함'}  {x.title}" for x in sub_r]
            lines.append(f"\n총 {len(rs)}개 규칙 (정적 + 렌더 실측, + 시각 루브릭: slop-lens rubric)")
            _out("\n".join(lines))
        return 0
    if a.cmd == "explain":
        from .mcp_server import explain_markdown
        rr = find_rule(a.rule_id)
        if not rr:
            print("해당 규칙이 없습니다.", file=sys.stderr)
            return 2
        _out(explain_markdown(rr))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
