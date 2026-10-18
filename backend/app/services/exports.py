"""CSV and PDF exports built from the same analysis results the UI shows."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from ..config import get_settings
from ..db import dumps, new_id, now
from .vocabulary import CRITERIA

DEMO_BANNER = "DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT"
DISCLAIMER = ("EarthTwin similarity indices are prototype indices computed from the data listed in this report. They are not "
              "probabilities of mission success and do not establish environmental equivalence. Earth cannot reproduce lunar or "
              "Martian gravity, vacuum/atmosphere or radiation. EarthTwin is an independent NASA Space Apps Challenge project and "
              "is not endorsed by NASA.")


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, list):
        return ";".join(map(str, v))
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def _record(conn, kind, target_id, params, assessment_ids, path):
    conn.execute("INSERT INTO exported_report(id, kind, target_region_id, params, assessment_ids, file_path, created_at) VALUES (?,?,?,?,?,?,?)",
                 (new_id(), kind, target_id, dumps(params), dumps(assessment_ids), str(path), now()))


def candidates_csv(conn, result: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    t = result["target"]
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    w.writerow([f"# EarthTwin candidate ranking — target: {t['name']} ({t['world_id']}); profile: {result['profile_name']}; generated {gen}"])
    w.writerow([f"# engine {result['engine_version']}; min coverage {result['thresholds']['min_coverage']}; "
                f"min criteria {result['thresholds']['min_criteria']}; demo data included: {result['include_demo']}"])
    if result["is_demo"]:
        w.writerow([f"# {DEMO_BANNER}: rows with is_demo=yes use illustrative values"])
    crit = [c.key for c in CRITERIA]
    w.writerow(["rank", "site_id", "site_name", "country", "lat", "lon", "status", "similarity_index", "weight_coverage",
                "criteria_used", "lowest_data_class", "is_demo", "strengths", "mismatches", "missing"]
               + [f"sim_{k}" for k in crit] + ["assessment_id", "input_hash", "engine_version"])
    for r in result["results"]:
        by = {c["criterion"]: c for c in r["criteria"]}
        w.writerow([r["rank"] or "", r["site"]["id"], r["site"]["name"], r["site"]["country"], r["site"]["lat"], r["site"]["lon"],
                    r["status"], _fmt(r["score"]), _fmt(r["coverage"]), r["n_criteria_used"], r["lowest_data_class"] or "",
                    _fmt(r["is_demo"]), ";".join(r["strengths"]), ";".join(r["mismatches"]), ";".join(r["missing"])]
                   + [_fmt(by[k]["similarity"]) if k in by else "" for k in crit]
                   + [r["assessment_id"] or "", r["input_hash"], r["engine_version"]])
    text = buf.getvalue()
    path = get_settings().export_dir / f"candidates-{t['id']}-{new_id()[:8]}.csv"
    path.write_text(text, encoding="utf-8")
    _record(conn, "candidates_csv", t["id"], {"profile": result["profile"], "weights": result["weights"]},
            [r["assessment_id"] for r in result["results"]], path)
    return text


def comparison_csv(conn, result: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    t = result["target"]
    w.writerow([f"# EarthTwin comparison — target: {t['name']} ({t['world_id']}); profile: {result['profile_name']}; "
                f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}"])
    if result["is_demo"]:
        w.writerow([f"# {DEMO_BANNER}"])
    w.writerow(["site_id", "site_name", "site_status", "similarity_index", "weight_coverage", "criterion", "family", "method",
                "weight", "site_value", "site_unit", "site_data_class", "target_value", "target_unit", "target_data_class",
                "similarity", "contribution_points", "criterion_status", "detail", "assessment_id"])
    for r in result["results"]:
        for c in r["criteria"]:
            w.writerow([r["site"]["id"], r["site"]["name"], r["status"], _fmt(r["score"]), _fmt(r["coverage"]), c["criterion"],
                        c["family"], c["method"], _fmt(c["weight"]), _fmt(c["site_value"]), c["site_unit"] or "", c["site_class"] or "",
                        _fmt(c["target_value"]), c["target_unit"] or "", c["target_class"] or "", _fmt(c["similarity"]),
                        _fmt(c["contribution"]), c["status"], c["detail"], r["assessment_id"] or ""])
    text = buf.getvalue()
    path = get_settings().export_dir / f"comparison-{t['id']}-{new_id()[:8]}.csv"
    path.write_text(text, encoding="utf-8")
    _record(conn, "comparison_csv", t["id"], {"sites": [r["site"]["id"] for r in result["results"]], "weights": result["weights"]},
            [r["assessment_id"] for r in result["results"]], path)
    return text


def report_pdf(conn, result: dict, target: dict, detail_sites: list[str], citations: list[dict], datasets: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as E

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, alignment=TA_LEFT, spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0b3a53"))
    H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
    P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=8.8, leading=11.5)
    S = ParagraphStyle("s", parent=P, fontSize=7.4, leading=9.2, textColor=colors.HexColor("#444444"))
    BAN = ParagraphStyle("ban", parent=P, fontSize=9.5, textColor=colors.HexColor("#7a4300"), backColor=colors.HexColor("#fff1d6"),
                         borderPadding=5, borderColor=colors.HexColor("#d98e04"), borderWidth=0.8, spaceAfter=8)

    def tbl(data, widths, header=True, size=7.4):
        t = Table([[Paragraph(E(str(c)), ParagraphStyle("c", parent=S, fontSize=size, leading=size + 1.8)) for c in r] for r in data],
                  colWidths=widths, repeatRows=1 if header else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c2cc")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if header:
            st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eef4")))
        t.setStyle(TableStyle(st))
        return t

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    buf = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(15 * mm, 9 * mm, f"EarthTwin by PLANEX · prototype similarity index · generated {gen}")
        canvas.drawRightString(195 * mm, 9 * mm, f"page {doc.page}")
        if result["is_demo"]:
            canvas.setFillColor(colors.HexColor("#b36200"))
            canvas.drawString(15 * mm, 287 * mm, DEMO_BANNER)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"EarthTwin report — {target['name']}", author="EarthTwin by PLANEX")
    el = [Paragraph("EarthTwin — Analog Comparison Report", H1),
          Paragraph(f"Target region: <b>{E(target['name'])}</b> ({E(target['world_id'].title())}) · Generated {gen}", P), Spacer(1, 4)]
    if result["is_demo"]:
        el.append(Paragraph(f"<b>{DEMO_BANNER}.</b> At least one input used below is an illustrative demonstration value. "
                            "Scores show how the method works, not a scientific finding.", BAN))
    el += [Paragraph("Target region", H2),
           Paragraph(f"{E(target.get('description') or '')}", P),
           Paragraph(f"<b>Geological context:</b> {E(target.get('geologic_context') or 'not documented')}", P),
           Paragraph(f"<b>Coordinates:</b> {target['lat']:.3f}°, {target['lon']:.3f}° (planetocentric, east-positive; {E(target['crs'])}); "
                     f"analysis window {target['analysis_radius_km']:g} km radius.", P)]
    tv = [[o["variable_key"], _fmt(o["value"]), o["unit"] or "", o["data_class"], o["dataset_name"]] for o in target["observations"]]
    if tv:
        el.append(tbl([["Variable", "Value", "Unit", "Data class", "Dataset"]] + tv, [42 * mm, 42 * mm, 18 * mm, 20 * mm, 58 * mm]))

    el += [Paragraph("Method", H2),
           Paragraph("Each criterion compares one Earth-site value with the target value of the same variable after unit "
                     "normalisation and yields a similarity between 0 and 1 (Gaussian on differences, Gaussian on log ratios, "
                     "Jaccard index for lithology sets, agreement for yes/no features). The index is the weight-normalised mean of "
                     "criteria with data on both sides × 100. Missing data never count as a match; weight coverage is reported "
                     f"separately and results below {result['thresholds']['min_coverage']:.0%} coverage or with fewer than "
                     f"{result['thresholds']['min_criteria']} criteria are reported as <b>insufficient data</b>. "
                     f"Engine version {result['engine_version']}. Weighting profile: <b>{E(result['profile_name'])}</b>.", P)]
    by = {c.key: c for c in CRITERIA}
    wrows = [[by[k].name, by[k].family, by[k].method, f"{v:g}"] for k, v in result["weights"].items() if k in by]
    el.append(tbl([["Criterion", "Family", "Method", "Weight"]] + wrows, [60 * mm, 30 * mm, 40 * mm, 20 * mm]))

    el.append(Paragraph("Candidate ranking", H2))
    rr = []
    for r in result["results"]:
        rr.append([r["rank"] or "—", r["site"]["name"], r["site"]["country"] or "",
                   "insufficient data" if r["status"] != "scored" else f"{r['score']:.1f}", f"{r['coverage']:.0%}",
                   str(r["n_criteria_used"]), r["lowest_data_class"] or "—"])
    el.append(tbl([["#", "Earth site", "Country", "Index", "Coverage", "Criteria", "Lowest data class"]] + rr,
                  [8 * mm, 52 * mm, 28 * mm, 26 * mm, 18 * mm, 16 * mm, 32 * mm]))

    details = [r for r in result["results"] if r["site"]["id"] in detail_sites] or [r for r in result["results"] if r["status"] == "scored"][:3]
    if details:
        el.append(PageBreak())
        el.append(Paragraph("Criterion-level results", H2))
    for r in details:
        block = [Paragraph(f"{E(r['site']['name'])} — " + ("insufficient data" if r["status"] != "scored" else f"index {r['score']:.1f}")
                           + f", coverage {r['coverage']:.0%}", H3)]
        if r["status"] != "scored":
            block.append(Paragraph(E(r.get("reason") or ""), S))
        rows_ = [[c["name"], f"{c['weight']:g}", f"{_fmt(c['site_value'])} {c['site_unit'] or ''}".strip(),
                  f"{_fmt(c['target_value'])} {c['target_unit'] or ''}".strip(),
                  "missing" if c["similarity"] is None else f"{c['similarity']:.2f}",
                  "" if c["contribution"] is None else f"{c['contribution']:.1f}", c["data_class"] or c["status"]]
                 for c in r["criteria"] if c["weight"] > 0]
        block.append(tbl([["Criterion", "Weight", "Earth site", "Target", "Similarity", "Points", "Class/status"]] + rows_,
                         [38 * mm, 14 * mm, 38 * mm, 38 * mm, 18 * mm, 14 * mm, 20 * mm]))
        mism = [c for c in r["criteria"] if c["criterion"] in r["mismatches"]]
        if mism:
            block.append(Paragraph("<b>Important differences:</b> " + "; ".join(f"{E(c['name'])} ({E(c['detail'])})" for c in mism), S))
        if r["missing"]:
            block.append(Paragraph("<b>Missing data (not counted):</b> " + ", ".join(E(by[m].name) for m in r["missing"] if m in by), S))
        el.append(KeepTogether(block))

    el.append(Paragraph("Data sources", H2))
    drows = [[d["name"], d["publisher"] or "", d["data_class"], d.get("version") or "", d["source_url"] or ""] for d in datasets]
    if drows:
        el.append(tbl([["Dataset", "Publisher", "Class", "Version", "Source"]] + drows, [52 * mm, 38 * mm, 18 * mm, 16 * mm, 56 * mm]))
    if citations:
        el.append(Paragraph("Citations", H3))
        for c in citations:
            extra = f" doi:{c['doi']}" if c.get("doi") else (f" {c['url']}" if c.get("url") else "")
            el.append(Paragraph(f"• {E(c['text'])}{E(extra)} <font color='#777777'>[{E(c['verification'])}]</font>", S))
    el += [Paragraph("Data classes", H2),
           Paragraph("<b>verified</b>: value from an identified dataset imported by the team · <b>derived</b>: calculated by the EarthTwin "
                     "pipeline from a verified input (e.g. slope from a DEM) · <b>demo</b>: illustrative value used to exercise the "
                     "application · <b>reference</b>: catalogue/context records without measurements.", P),
           Paragraph("Limitations", H2), Paragraph(E(DISCLAIMER), P),
           Paragraph("Absolute elevations are never compared between bodies; terrain statistics depend on DEM resolution and window size, "
                     "which are recorded per value. Temperature criteria use window means and do not capture cold-trap extremes.", P)]
    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    pdf = buf.getvalue()
    path = get_settings().export_dir / f"report-{target['id']}-{new_id()[:8]}.pdf"
    path.write_bytes(pdf)
    _record(conn, "report_pdf", target["id"], {"profile": result["profile"], "weights": result["weights"], "detail_sites": detail_sites},
            [r["assessment_id"] for r in result["results"]], path)
    return pdf
