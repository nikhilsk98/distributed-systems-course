"""Build THE presentation: ../PRESENTATION_Experiment_Presentation.pptx (python-pptx, 16:9).

Slide text is kept short; numbers are filled from results/*/summary_*.csv so the deck always
matches the data. Speaker notes carry the timed script (also in PRESENTATION_talking_points.md).
usage: python build_presentation.py
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from common import DELIV

FIG, SHOT = DELIV / "figures", DELIV / "screenshots"
OUT = DELIV / "PRESENTATION_Experiment_Presentation.pptx"
CONTENT = json.loads((Path(__file__).parent / "presentation_content.json").read_text())

NAVY = RGBColor(0x14, 0x21, 0x3D)
INK = RGBColor(0x1F, 0x1F, 0x1F)
MUTED = RGBColor(0x5A, 0x5A, 0x5A)
ACCENT = RGBColor(0xE8, 0x6A, 0x33)   # UDP-orange accent, used sparingly
TINT = RGBColor(0xEE, 0xF2, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD, BODY = "Cambria", "Calibri"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = prs.slide_width, prs.slide_height


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=16, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT, name=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(8)
        r = para.add_run()
        r.text = p
        r.font.size, r.font.color.rgb, r.font.name, r.font.bold = Pt(size), color, font, bold
    return tb


def title(slide, t, sub=None, dark=False):
    text(slide, Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.9), t, size=34, font=HEAD, bold=True,
         color=WHITE if dark else NAVY, name="Title")
    if sub:
        text(slide, Inches(0.6), Inches(1.15), Inches(12.1), Inches(0.5), sub, size=16, color=MUTED if not dark else TINT, name="Subtitle")


def bullets(slide, x, y, w, h, items, size=16):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tb.name = "Bullets"
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        bold, rest = (it.split("|", 1) + [""])[:2] if "|" in it else ("", it)
        if bold:
            r = p.add_run()
            r.text = bold + " "
            r.font.bold, r.font.size, r.font.color.rgb, r.font.name = True, Pt(size), NAVY, BODY
        r = p.add_run()
        r.text = rest
        r.font.size, r.font.color.rgb, r.font.name = Pt(size), INK, BODY
    return tb


def card(slide, x, y, w, h, big, label, color=NAVY):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    s.name = "StatCard"
    s.fill.solid()
    s.fill.fore_color.rgb = TINT
    s.line.fill.background()
    s.adjustments[0] = 0.08
    text(slide, x + Inches(0.2), y + Inches(0.12), w - Inches(0.4), Inches(0.9), big, size=36, font=HEAD, bold=True, color=color)
    text(slide, x + Inches(0.2), y + Inches(0.95), w - Inches(0.4), h - Inches(1.0), label, size=13, color=MUTED)


def picture(slide, path, x, y, w=None, h=None, caption=None):
    pic = slide.shapes.add_picture(str(path), x, y, width=w, height=h)
    pic.name = Path(path).stem
    if caption:
        text(slide, x, pic.top + pic.height + Inches(0.05), pic.width, Inches(0.4), caption, size=11, color=MUTED)
    return pic


def fit(path, max_w, max_h):
    from PIL import Image
    iw, ih = Image.open(path).size
    s = min(max_w / iw, max_h / ih)
    return Emu(int(iw * s)), Emu(int(ih * s))


def figure_slide(spec):
    s = prs.slides.add_slide(BLANK)
    bg(s, WHITE)
    title(s, spec["title"], spec.get("subtitle"))
    img = FIG / spec["figure"] if (FIG / spec["figure"]).exists() else SHOT / spec["figure"]
    left_w = Inches(7.9) if spec.get("bullets") else Inches(12.1)
    w, h = fit(img, left_w, Inches(5.3))
    picture(s, img, Inches(0.6), Inches(1.75), w, h, spec.get("caption"))
    if spec.get("bullets"):
        bullets(s, Inches(8.8), Inches(1.9), Inches(4.0), Inches(5.0), spec["bullets"], size=16)
    s.notes_slide.notes_text_frame.text = spec["notes"]


for spec in CONTENT["slides"]:
    kind = spec["kind"]
    if kind == "title":
        s = prs.slides.add_slide(BLANK)
        bg(s, NAVY)
        text(s, Inches(0.8), Inches(0.6), Inches(11.5), Inches(0.4), "THE PRESENTATION · CS6650 Midterm Mastery Part 2 (empirical)", size=14, color=TINT, bold=True)
        text(s, Inches(0.8), Inches(2.0), Inches(11.5), Inches(1.8), spec["title"], size=44, font=HEAD, bold=True, color=WHITE)
        text(s, Inches(0.8), Inches(3.9), Inches(11.5), Inches(1.0), spec["subtitle"], size=20, color=TINT)
        text(s, Inches(0.8), Inches(6.3), Inches(11.5), Inches(0.5), spec["byline"], size=14, color=TINT)
        s.notes_slide.notes_text_frame.text = spec["notes"]
    elif kind == "figure":
        figure_slide(spec)
    elif kind == "stats":
        s = prs.slides.add_slide(BLANK)
        bg(s, WHITE)
        title(s, spec["title"], spec.get("subtitle"))
        n = len(spec["cards"])
        cw = (Inches(12.1) - Inches(0.3) * (n - 1)) / n
        for i, (big, label) in enumerate(spec["cards"]):
            card(s, Inches(0.6) + i * (cw + Inches(0.3)), Inches(1.9), int(cw), Inches(1.9), big, label, ACCENT if i == 0 else NAVY)
        if spec.get("figure"):
            img = FIG / spec["figure"] if (FIG / spec["figure"]).exists() else SHOT / spec["figure"]
            w, h = fit(img, Inches(7.4), Inches(3.2))
            picture(s, img, Inches(0.6), Inches(4.05), w, h)
            bullets(s, Inches(8.3), Inches(4.1), Inches(4.5), Inches(3.2), spec.get("bullets", []), size=15)
        else:
            bullets(s, Inches(0.6), Inches(4.2), Inches(12.1), Inches(3.0), spec.get("bullets", []), size=17)
        s.notes_slide.notes_text_frame.text = spec["notes"]
    elif kind == "table":
        s = prs.slides.add_slide(BLANK)
        bg(s, WHITE)
        title(s, spec["title"], spec.get("subtitle"))
        rows, cols = len(spec["rows"]), len(spec["rows"][0])
        tbl = s.shapes.add_table(rows, cols, Inches(0.6), Inches(1.8), Inches(12.1), Inches(0.5) * rows).table
        for c, wd in enumerate(spec.get("widths", [])):
            tbl.columns[c].width = Inches(wd)
        for r, row in enumerate(spec["rows"]):
            for c, val in enumerate(row):
                cell = tbl.cell(r, c)
                cell.text = val
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size, run.font.name = Pt(14), BODY
                        run.font.bold = r == 0 or c == 0
                        run.font.color.rgb = WHITE if r == 0 else INK
                cell.fill.solid()
                cell.fill.fore_color.rgb = NAVY if r == 0 else (TINT if r % 2 else WHITE)
        if spec.get("footer"):
            text(s, Inches(0.6), Inches(1.8) + Inches(0.5) * rows + Inches(0.3), Inches(12.1), Inches(1.2), spec["footer"], size=15, color=MUTED)
        s.notes_slide.notes_text_frame.text = spec["notes"]
    elif kind == "closing":
        s = prs.slides.add_slide(BLANK)
        bg(s, NAVY)
        title(s, spec["title"], dark=True)
        y = Inches(1.6)
        for i, (head, body) in enumerate(spec["items"]):
            circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.7), y + Inches(0.05), Inches(0.55), Inches(0.55))
            circ.fill.solid()
            circ.fill.fore_color.rgb = ACCENT
            circ.line.fill.background()
            tf = circ.text_frame
            tf.text = str(i + 1)
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
            tf.paragraphs[0].runs[0].font.size, tf.paragraphs[0].runs[0].font.bold = Pt(18), True
            tf.paragraphs[0].runs[0].font.color.rgb = WHITE
            text(s, Inches(1.5), y - Inches(0.02), Inches(11.2), Inches(0.45), head, size=20, bold=True, color=WHITE)
            text(s, Inches(1.5), y + Inches(0.42), Inches(11.2), Inches(0.6), body, size=15, color=TINT)
            y += Inches(1.12)
        s.notes_slide.notes_text_frame.text = spec["notes"]

prs.core_properties.title = "File-transfer service: three experiments"
prs.core_properties.author = "Nikhil Shivakumar"
prs.core_properties.last_modified_by = "Nikhil Shivakumar"
prs.save(OUT)
print("saved", OUT)

# ---- timed talking points from the same speaker notes (150 words/min) ----
lines = ["# THE presentation: timed talking points",
         "",
         "Script for [`PRESENTATION_Experiment_Presentation.pptx`](PRESENTATION_Experiment_Presentation.pptx) / `.pdf`. The same text is in each slide's speaker notes. Times assume about 150 words per minute.",
         ""]
t = 0
for i, spec in enumerate(CONTENT["slides"], 1):
    words = len(spec["notes"].split())
    secs = round(words / 150 * 60)
    lines += [f"## Slide {i} ({t // 60}:{t % 60:02d}–{(t + secs) // 60}:{(t + secs) % 60:02d}, ~{secs} s): {spec['title']}",
              "", f"*On screen:* {spec.get('figure', 'title / summary')}", "", spec["notes"], ""]
    t += secs
lines.insert(3, f"**Total: about {t // 60} min {t % 60:02d} s.**\n")
(DELIV / "PRESENTATION_talking_points.md").write_text("\n".join(lines))
print("saved talking points, total", t, "s")
