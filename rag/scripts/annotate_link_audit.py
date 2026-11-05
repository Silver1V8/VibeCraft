"""Annotazione guidata delle schede IMPLEMENTS (cieca rispetto al sigillo).

Chiamato da CLI: `uv run python scripts/annotate_link_audit.py …`.
Nessuno script equivalente esisteva (solo sample/validate/metrics in link_audit.py).
Legge/scrive schede.json e suggestions_draft.json:
  {edge_id, label, motivation, confirmed?} — senza date.
Istruzione utente: «Aiutami a Annotare le 80 schede IMPLEMENTS, poi validate + metrics.»
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LABELS = ("IMPLEMENTA", "CORRELATO", "ERRATO", "NON_VALUTABILE")
DEFAULT_RUN = Path(__file__).resolve().parents[3] / "projects" / "legacy" / "eval" / "link_audit" / "2026-11-01"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_status(args) -> int:
    run = Path(args.run)
    cards = _read(run / "schede.json")
    labeled = [c for c in cards if c.get("label") in LABELS]
    print(json.dumps({
        "run": str(run),
        "n": len(cards),
        "labeled": len(labeled),
        "missing": len(cards) - len(labeled),
        "by_label": {lab: sum(1 for c in labeled if c["label"] == lab) for lab in LABELS},
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_show(args) -> int:
    run = Path(args.run)
    cards = _read(run / "schede.json")
    draft_path = run / "suggestions_draft.json"
    draft = {d["edge_id"]: d for d in (_read(draft_path) if draft_path.is_file() else [])}
    start = args.offset
    end = min(len(cards), start + args.n)
    for i, c in enumerate(cards[start:end], start=start):
        sug = draft.get(c["edge_id"], {})
        print("=" * 72)
        print(f"[{i}] edge_id={c['edge_id']}  kind={c.get('kind')}  status_scheda={c.get('label') or 'VUOTA'}")
        print(f"CODICE: {c.get('symbol_id')}")
        print(f"FILE:   {c.get('file')}")
        print(f"NORMA:  {c.get('target_doc_id')} § {c.get('target_section')}")
        print("--- symbol_text ---")
        print((c.get("symbol_text") or "")[:900])
        print("--- target_text ---")
        print((c.get("target_text") or "")[:900])
        if sug:
            print(f"--- DRAFT (non ancora ground truth) → {sug.get('label')} ---")
            print(sug.get("motivation", ""))
        print()
    print(f"Mostrate {start}..{end - 1} di {len(cards)}. Prosegui con --offset {end}")
    return 0


def cmd_apply(args) -> int:
    if not args.i_confirm:
        print("Rifiutato: passa --i-confirm per attestare di aver revisionato le etichette.", file=sys.stderr)
        return 2
    annotator = (args.annotator or "").strip()
    if not annotator:
        print("Serve --annotator (il tuo identificativo umano).", file=sys.stderr)
        return 2
    run = Path(args.run)
    cards = _read(run / "schede.json")
    draft = _read(run / "suggestions_draft.json")
    by_id = {d["edge_id"]: d for d in draft}
    applied = 0
    skipped = 0
    for card in cards:
        d = by_id.get(card["edge_id"])
        if not d or not d.get("confirmed"):
            skipped += 1
            continue
        label = d.get("label")
        motivation = str(d.get("motivation") or "").strip()
        if label not in LABELS or len(motivation) < 20:
            print(f"Draft invalido per {card['edge_id']}: label/motivation", file=sys.stderr)
            return 1
        card["label"] = label
        card["motivation"] = motivation
        card["annotator"] = annotator
        applied += 1
    backup = run / "schede.json.bak"
    if not backup.exists():
        backup.write_text((run / "schede.json").read_text(encoding="utf-8"), encoding="utf-8")
    _write(run / "schede.json", cards)
    print(json.dumps({"applied": applied, "skipped_unconfirmed_or_missing": skipped, "annotator": annotator}, indent=2))
    return 0


def cmd_confirm_all_draft(args) -> int:
    if not args.i_reviewed_all:
        print("Rifiutato: passa --i-reviewed-all solo dopo aver letto le bozze.", file=sys.stderr)
        return 2
    run = Path(args.run)
    draft = _read(run / "suggestions_draft.json")
    for d in draft:
        d["confirmed"] = True
    _write(run / "suggestions_draft.json", draft)
    print(f"Confirmate {len(draft)} bozze. Ora: apply --annotator … --i-confirm")
    return 0


def cmd_dual_compare(args) -> int:
    """Confronta schede A vs dual_schede_B. Non pubblica GT; scrive report locale."""
    run = Path(args.run)
    a_cards = {c["edge_id"]: c for c in _read(run / "schede.json")}
    b_cards = {c["edge_id"]: c for c in _read(run / "dual_schede_B.json")}
    subset = _read(run / "dual_subset.json")["edge_ids"]
    agree, disagree, rows = [], [], []
    for eid in subset:
        a_lab = (a_cards.get(eid) or {}).get("label")
        b = b_cards.get(eid) or {}
        b_lab = b.get("label")
        if a_lab not in LABELS or b_lab not in LABELS:
            disagree.append(eid)
            rows.append({"edge_id": eid, "A": a_lab, "B": b_lab, "agree": False, "reason": "missing_label"})
            continue
        ok = a_lab == b_lab
        (agree if ok else disagree).append(eid)
        rows.append({
            "edge_id": eid, "A": a_lab, "B": b_lab, "agree": ok,
            "B_annotator": b.get("annotator"), "B_not_human_gt": b.get("not_human_gt"),
        })
    report = {
        "status": "dual_compare",
        "n": len(subset),
        "agree": len(agree),
        "disagree": len(disagree),
        "agreement_rate": round(len(agree) / len(subset), 4) if subset else None,
        "human_gt": not any((b_cards.get(e) or {}).get("not_human_gt") for e in subset),
        "disagreements": disagree,
        "rows": rows,
    }
    out = run / "dual_agreement_provisional.json"
    _write(out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Scritto {out}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Annotazione schede IMPLEMENTS")
    p.add_argument("--run", default=str(DEFAULT_RUN))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)

    sh = sub.add_parser("show")
    sh.add_argument("--offset", type=int, default=0)
    sh.add_argument("--n", type=int, default=5)
    sh.set_defaults(func=cmd_show)

    a = sub.add_parser("apply")
    a.add_argument("--annotator", required=True)
    a.add_argument("--i-confirm", action="store_true")
    a.set_defaults(func=cmd_apply)

    c = sub.add_parser("confirm-all-draft")
    c.add_argument("--i-reviewed-all", action="store_true")
    c.set_defaults(func=cmd_confirm_all_draft)

    d = sub.add_parser("dual-compare", help="Accordo A vs dual_schede_B (report locale)")
    d.set_defaults(func=cmd_dual_compare)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
