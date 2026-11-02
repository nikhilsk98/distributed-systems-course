"""Render a terminal-output text file as a PNG (monospace, dark terminal look).
usage: python text_to_png.py input.txt output.png [--title T] [--max-lines 60]
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("--title", default="")
ap.add_argument("--max-lines", type=int, default=60)
ap.add_argument("--width", type=int, default=150)
a = ap.parse_args()
import re
lines = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", open(a.src).read()).splitlines()
if len(lines) > a.max_lines:
    lines = lines[: a.max_lines - 1] + [f"... ({len(lines) - a.max_lines + 1} more lines in {a.src.split('/')[-1]})"]
lines = [l if len(l) <= a.width else l[: a.width - 1] + "…" for l in lines]
h = 0.6 + 0.19 * (len(lines) + (2 if a.title else 0))
fig = plt.figure(figsize=(min(18, 0.085 * max(len(l) for l in lines + [a.title]) + 1), h), facecolor="#1a1a19")
text = (f"$ {a.title}\n\n" if a.title else "") + "\n".join(lines)
fig.text(0.01, 0.98, text, family="monospace", fontsize=10, color="#f0efec", va="top", ha="left")
fig.savefig(a.dst, dpi=140, facecolor="#1a1a19")
print("png", a.dst)
