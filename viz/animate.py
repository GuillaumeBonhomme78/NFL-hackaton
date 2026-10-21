"""Animation d'une action avec le Pocket Clock en direct (docs/play_<gameId>_<playId>.gif).

Pensé pour un commentateur : chrono depuis le snap, rayon de 2 yd autour du QB,
rusher le plus proche et jauge de pression, image par image.

Usage : python viz/animate.py [gameId playId]   (par défaut : sack de Myles Garrett sur Mahomes, semaine 1)
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from common import BAD, BREACH_RADIUS, DATA, DOCS, FPS, GOOD, KEYS, OUT  # noqa: E402

DEFAULT_PLAY = (2021091209, 3639)
FIELD_LENGTH, FIELD_WIDTH = 120, 53.3
VIEW_BACK, VIEW_FRONT, VIEW_SIDE = 10, 12, 13   # yards autour du QB au snap
PRE_SNAP_FRAMES, POST_END_FRAMES, HOLD_FRAMES = 3, 8, 15
OFFENSE, DEFENSE, RUSHER, QB, BALL = "#457b9d", "#f4a3a8", BAD, "#f4a261", "#6d4c41"


def load_play(game_id, play_id):
    plays = pd.read_csv(OUT / "plays.csv")
    play = plays[(plays.gameId == game_id) & (plays.playId == play_id)]
    if play.empty:
        sys.exit(f"Action {game_id}/{play_id} absente de outputs/plays.csv (action de passe avec snap tagué ?)")
    play = play.iloc[0]

    trk = pd.read_csv(DATA / "tracking" / f"tracking_{game_id}.csv",
                      usecols=KEYS + ["nflId", "frameId", "jerseyNumber", "team", "playDirection", "x", "y"])
    trk = trk[trk.playId == play_id].copy()
    if trk.playDirection.iloc[0] == "left":  # l'attaque joue toujours vers la droite
        trk["x"], trk["y"] = FIELD_LENGTH - trk.x, FIELD_WIDTH - trk.y

    pff = pd.read_csv(DATA / "pffScoutingData.csv", usecols=KEYS + ["nflId", "pff_role"])
    roles = pff[(pff.gameId == game_id) & (pff.playId == play_id)][["nflId", "pff_role"]]
    trk = trk.merge(roles, on="nflId", how="left")

    frames = pd.read_parquet(OUT / "frames.parquet", filters=[("gameId", "==", game_id), ("playId", "==", play_id)])
    names = pd.read_csv(DATA / "players.csv", usecols=["nflId", "displayName"]).set_index("nflId").displayName
    return play, trk, frames.set_index("frameId"), names


def draw_field(ax, x0, y0, los):
    ax.set_facecolor("#eef6ef")
    ax.set(xlim=(x0 - VIEW_BACK, x0 + VIEW_FRONT), ylim=(y0 - VIEW_SIDE, y0 + VIEW_SIDE), aspect="equal")
    ax.set_xticks([]), ax.set_yticks([])
    for x in range(0, FIELD_LENGTH + 1, 5):
        ax.axvline(x, color="white", lw=1.5, zorder=0)
    ax.axvline(los, color=OFFENSE, lw=1, ls="--", alpha=0.6, zorder=0)


def player_style(row, offense):
    if row.team == "football":
        return BALL, 40
    if row.pff_role == "Pass":
        return QB, 260
    if row.pff_role == "Pass Rush":
        return RUSHER, 200
    return (OFFENSE if row.team == offense else DEFENSE), 170


def draw_players(ax, snap, offense):
    for row in snap.itertuples():
        color, size = player_style(row, offense)
        ax.scatter(row.x, row.y, s=size, color=color, edgecolor="white", lw=0.8, zorder=3)
        if row.team != "football":
            ax.text(row.x, row.y, int(row.jerseyNumber), ha="center", va="center",
                    fontsize=6, color="white", fontweight="bold", zorder=4)


def draw_pocket(ax, snap, info, breached):
    qb = snap[snap.pff_role == "Pass"]
    if qb.empty:
        return
    qx, qy = qb.x.iloc[0], qb.y.iloc[0]
    color = BAD if breached else GOOD
    ax.add_patch(Circle((qx, qy), BREACH_RADIUS, color=color, alpha=0.18, zorder=1))
    ax.add_patch(Circle((qx, qy), BREACH_RADIUS, fill=False, ec=color, lw=1.5, ls="--", zorder=1))
    if info is None:
        return
    rusher = snap[snap.nflId == info.closest_rusher]
    if rusher.empty:
        return
    rx, ry = rusher.x.iloc[0], rusher.y.iloc[0]
    ax.plot([qx, rx], [qy, ry], color=color, lw=1.2, zorder=2)
    ax.text((qx + rx) / 2, (qy + ry) / 2 + 0.6, f"{info.closest_dist:.1f} yd", fontsize=8,
            color=color, ha="center", fontweight="bold", zorder=5)


def draw_legend(ax):
    items = [(QB, "QB"), (RUSHER, "pass rusher"), (OFFENSE, "attaque"), (DEFENSE, "couverture")]
    handles = [Line2D([], [], marker="o", ls="", color=c, markeredgecolor="white", markersize=8, label=label)
               for c, label in items]
    handles.append(Line2D([], [], color=GOOD, ls="--", label=f"rayon {BREACH_RADIUS:.0f} yd"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=5, fontsize=7,
              frameon=False, handletextpad=0.2, columnspacing=0.8)


def draw_panel(ax, t, gauge, play, breached, ended, names):
    ax.clear()
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ax.text(0.5, 0.94, "POCKET CLOCK", ha="center", fontsize=10, fontweight="bold", color="0.3")
    ax.text(0.5, 0.80, "pré-snap" if t < 0 else f"{t:.1f} s", ha="center", fontsize=24, fontweight="bold")
    ax.add_patch(Rectangle((0.3, 0.30), 0.4, 0.38, fill=False, ec="0.5"))
    ax.add_patch(Rectangle((0.3, 0.30), 0.4, 0.38 * gauge, color=plt.cm.RdYlGn_r(gauge)))
    ax.text(0.5, 0.25, f"pression {gauge:.0%}", ha="center", fontsize=9)
    if breached:
        status = f"PERCÉE à {play.breach_time:.1f} s\npar {names.get(play.breach_rusher, '?')}"
    else:
        status = "Poche intacte"
    ax.text(0.5, 0.11, status, ha="center", va="center", fontsize=9, fontweight="bold",
            color=BAD if breached else GOOD)
    if ended:
        outcome = {"S": "SACK", "C": "Passe complète", "I": "Passe incomplète",
                   "IN": "Interception", "R": "Scramble"}.get(play.passResult, play.passResult)
        ax.text(0.5, 0.01, f"{outcome} ({play.playResult:+d} yd)", ha="center", fontsize=9)


def animate(game_id, play_id):
    play, trk, frames, names = load_play(game_id, play_id)
    snap_frame, end_frame = int(play.snap_frame), int(play.end_frame)
    first = max(trk.frameId.min(), snap_frame - PRE_SNAP_FRAMES)
    last = min(trk.frameId.max(), end_frame + POST_END_FRAMES)
    sequence = list(range(first, last + 1)) + [last] * HOLD_FRAMES

    at_snap = trk[trk.frameId == snap_frame]
    qb0 = at_snap[at_snap.pff_role == "Pass"]
    ball0 = at_snap[at_snap.team == "football"]
    x0, y0 = (qb0 if not qb0.empty else ball0)[["x", "y"]].iloc[0]
    los = ball0.x.iloc[0] if not ball0.empty else x0

    fig, (field, panel) = plt.subplots(1, 2, figsize=(8, 6), gridspec_kw={"width_ratios": [2.4, 1]})
    fig.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.07, wspace=0.05)
    desc = play.playDescription if len(play.playDescription) <= 90 else play.playDescription[:87] + "..."
    fig.suptitle(f"{play.possessionTeam} (bleu) vs {play.defensiveTeam} (rouge) : {desc}", fontsize=9)

    def update(frame_id):
        field.clear()
        draw_field(field, x0, y0, los)
        snap = trk[trk.frameId == frame_id]
        clock_frame = min(frame_id, end_frame)  # chrono et jauge figés à la passe / au sack
        t = (clock_frame - snap_frame) / FPS
        info = frames.loc[clock_frame] if clock_frame in frames.index else None
        breached = play.breached and t >= play.breach_time
        draw_players(field, snap, play.possessionTeam)
        draw_pocket(field, snap, info if frame_id <= end_frame else None, breached)
        draw_legend(field)
        gauge = info.pressure_gauge if info is not None else 0.0
        draw_panel(panel, t, gauge, play, breached, frame_id >= end_frame, names)

    anim = FuncAnimation(fig, update, frames=sequence)
    DOCS.mkdir(exist_ok=True)
    path = DOCS / f"play_{game_id}_{play_id}.gif"
    anim.save(path, writer=PillowWriter(fps=FPS), dpi=80)
    plt.close(fig)
    print("écrit :", path)


def main():
    if len(sys.argv) not in (1, 3):
        sys.exit("Usage : python viz/animate.py [gameId playId]")
    game_id, play_id = map(int, sys.argv[1:]) if len(sys.argv) == 3 else DEFAULT_PLAY
    animate(game_id, play_id)


if __name__ == "__main__":
    main()
