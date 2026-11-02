"""Draw the service architecture diagram used in the slides (figures/architecture.png)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from common import DELIV

INK, INK2, BLUE, ORANGE, AQUA, TINT = "#0b0b0b", "#52514e", "#2a78d6", "#eb6834", "#1baf7a", "#eef2f8"
fig, ax = plt.subplots(figsize=(13, 5.2))
ax.set_xlim(0, 13)
ax.set_ylim(0, 5.2)
ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, title, sub, edge):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=TINT, ec=edge, lw=2))
    ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=13, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=10, color=INK2)


def arrow(x0, y0, x1, y1, label, color=INK2, dy=0.18):
    ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2 + dy, label, ha="center", fontsize=9.5, color=color)


box(0.1, 2.0, 1.7, 1.2, "Locust", "laptop, HTTP", INK2)
box(2.4, 2.0, 1.6, 1.2, "ALB", "HTTP :80", BLUE)
box(4.6, 3.1, 2.0, 1.2, "gateway task", "Gin + UDP client\nMAX_INFLIGHT=4", BLUE)
box(4.6, 0.9, 2.0, 1.2, "gateway task", "(2–4 tasks)", BLUE)
box(7.2, 2.0, 1.6, 1.2, "NLB", "UDP :8080", ORANGE)
box(9.4, 3.1, 2.0, 1.2, "backend task", "UDP server\n8 workers, queue 32", ORANGE)
box(9.4, 0.9, 2.0, 1.2, "backend task", "(2–4 tasks)", ORANGE)
box(11.75, 2.0, 1.15, 1.2, "S3", "tmp/ prefix", AQUA)
arrow(1.8, 2.6, 2.4, 2.6, "GET /files")
arrow(4.0, 2.75, 4.6, 3.5, "")
arrow(4.0, 2.45, 4.6, 1.6, "")
arrow(6.6, 3.5, 7.2, 2.75, "OPEN / RETY", ORANGE, 0.25)
arrow(6.6, 1.6, 7.2, 2.45, "")
arrow(8.8, 2.75, 9.4, 3.5, "")
arrow(8.8, 2.45, 9.4, 1.6, "")
arrow(11.4, 3.5, 11.9, 3.2, "", AQUA)
arrow(11.4, 1.6, 11.9, 2.0, "", AQUA)
ax.text(11.6, 4.55, "GetObject on EVERY\nOPEN and RETY", ha="center", fontsize=9.5, color=AQUA, fontweight="bold")
ax.annotate("", (6.6, 4.1), (9.4, 4.1), arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.4, ls="--",
            connectionstyle="arc3,rad=-0.25"))
ax.text(8.0, 4.85, "64-byte chunk datagrams, sent back-to-back (1 MB = 16,384)", ha="center", fontsize=10, color=ORANGE)
ax.text(5.6, 0.35, "scales on ALBRequestCountPerTarget (100 req/min)", ha="center", fontsize=10, color=BLUE)
ax.text(10.4, 0.35, "scales on ECS CPU (60%)", ha="center", fontsize=10, color=ORANGE)
fig.savefig(DELIV / "figures" / "architecture.png", dpi=160, bbox_inches="tight")
print("figure architecture.png")
