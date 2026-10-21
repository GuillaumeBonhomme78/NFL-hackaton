"""Dashboard interactif du Pocket Clock (docs/dashboard.html), interface « salle de contrôle ».

Ce script prépare les données (courbes de survie, équipes, joueurs, actions rejouées) et les injecte
dans le gabarit viz/web/ (template.html, style.css, *.js) pour produire une page unique, sans serveur.
Plotly et les polices sont chargés depuis leur CDN : il faut une connexion à l'ouverture.
"""
import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs_version

from animate import POST_END_FRAMES, PRE_SNAP_FRAMES, load_play
from common import BREACH_RADIUS, DATA, DOCS, KEYS, KM_GRID, LEAGUE, load_outputs, spearman, survival_curves
from pocket import auc

WEB = Path(__file__).resolve().parent / "web"
JS_FILES = ["core.js", "replay.js", "app.js"]  # dans l'ordre : app.js démarre la page
FEATURED_PLAYS = [  # (gameId, playId, titre), vérifiés dans outputs/plays.csv
    (2021091209, 3639, "Sack de Myles Garrett"),
    (2021092611, 2280, "Poche intacte, TD de 75 yd"),
    (2021102400, 2422, "Sack de Trey Hendrickson"),
    (2021101001, 2821, "Percée éclair de Haason Reddick"),
]
ROLES = {"Pass": "qb", "Pass Rush": "rush", "Pass Block": "block"}
OFFENSE_ROLES = ["Pass", "Pass Block", "Pass Route"]


def records(df):
    """Lignes d'un DataFrame en dicts JSON (NaN -> null)."""
    return json.loads(df.to_json(orient="records", double_precision=4))


def curve(values):
    return [round(float(v), 4) for v in values]


def player_teams():
    """Équipe de chaque joueur : celle avec laquelle il a joué le plus d'actions."""
    pff = pd.read_csv(DATA / "pffScoutingData.csv", usecols=KEYS + ["nflId", "pff_role"])
    plays = pd.read_csv(DATA / "plays.csv", usecols=KEYS + ["possessionTeam", "defensiveTeam"])
    df = pff.merge(plays, on=KEYS)
    df["team"] = df.possessionTeam.where(df.pff_role.isin(OFFENSE_ROLES), df.defensiveTeam)
    return df.groupby("nflId").team.agg(lambda s: s.mode().iat[0])


def team_records(table, team_col, curves):
    rows = records(table.rename(columns={team_col: "team"}))
    return [{**row, "curve": curve(curves[row["team"]])} for row in rows]


def player_record(row, offense):
    if row.team == "football":
        return {"jersey": None, "side": "ball", "role": "ball"}
    return {"jersey": int(row.jerseyNumber), "side": "off" if row.team == offense else "def",
            "role": ROLES.get(row.pff_role, "other")}


def frame_record(frame_id, xy, pids, frames, index):
    """Positions de tous les joueurs à une image + rusher le plus proche et jauge (entre snap et passe)."""
    points = []
    for pid in pids:
        x, y = xy.at[frame_id, ("x", pid)], xy.at[frame_id, ("y", pid)]
        points.append(None if pd.isna(x) else [round(float(x), 2), round(float(y), 2)])
    rec = {"f": frame_id, "p": points, "d": None, "r": None, "g": None}
    if frame_id in frames.index:
        info = frames.loc[frame_id]
        rec.update(d=round(float(info.closest_dist), 2), r=index.get(int(info.closest_rusher)),
                   g=round(float(info.pressure_gauge), 3))
    return rec


def replay_record(game_id, play_id, title, weeks):
    play, trk, frames, names = load_play(game_id, play_id)
    snap, end = int(play.snap_frame), int(play.end_frame)
    first = max(int(trk.frameId.min()), snap - PRE_SNAP_FRAMES)
    last = min(int(trk.frameId.max()), end + POST_END_FRAMES)
    trk = trk[trk.frameId.between(first, last)].assign(pid=lambda d: d.nflId.fillna(0).astype(int))
    roster = trk.drop_duplicates("pid").sort_values("pid")
    index = {pid: i for i, pid in enumerate(roster.pid)}
    xy = trk.pivot(index="frameId", columns="pid", values=["x", "y"]).reindex(range(first, last + 1))

    at_snap = trk[trk.frameId == snap]
    qb, ball = at_snap[at_snap.pff_role == "Pass"], at_snap[at_snap.team == "football"]
    center = (qb if not qb.empty else ball)[["x", "y"]].iloc[0]
    los = float(ball.x.iloc[0]) if not ball.empty else float(center.x)
    return {
        "title": title, "week": int(weeks[game_id]), "offense": play.possessionTeam, "defense": play.defensiveTeam,
        "description": play.playDescription, "down": int(play.down), "yardsToGo": int(play.yardsToGo),
        "result": play.passResult, "yards": int(play.playResult),
        "breachTime": None if pd.isna(play.breach_time) else float(play.breach_time),
        "breachRusher": names.get(int(play.breach_rusher)) if play.breached else None,
        "snap": snap, "end": end, "endIndex": end - first,
        "los": round(los, 2), "firstDown": round(los + float(play.yardsToGo), 2),
        "center": [round(float(center.x), 2), round(float(center.y), 2)],
        "players": [player_record(r, play.possessionTeam) for r in roster.itertuples()],
        "frames": [frame_record(f, xy, roster.pid, frames, index) for f in range(first, last + 1)],
    }


def kpis(plays, off, rushers, blockers, league):
    return {
        "leagueClock": float(league[league < 0.5].index[0]),
        "intact25": float(league[2.5]),
        "agreement": float((plays.breached == plays.pff_pressure).mean()),
        "auc": float(auc(-plays.min_dist.fillna(99), plays.pff_pressure)),
        "rhoClock": float(spearman(off.pocket_clock, off.yards_per_play)),
        "rhoPff": float(spearman(off.pff_pressure_rate, off.yards_per_play)),
        "rRushers": float(rushers.breach_rate.corr(rushers.pff_pressure_rate)),
        "rBlockers": float(blockers.breach_allowed_rate.corr(blockers.pff_allowed_rate)),
        "plays": len(plays), "radius": BREACH_RADIUS,
        "minPlays": int(off.plays.min()), "maxPlays": int(off.plays.max()),
    }


def build_payload():
    out = load_outputs()
    plays, off, dfn = out["plays"], out["teams_offense"], out["teams_defense"]
    curves_off = survival_curves(plays, "possessionTeam")
    curves_def = survival_curves(plays, "defensiveTeam")
    teams = pd.concat([curves_off.drop(columns=LEAGUE), curves_def.drop(columns=LEAGUE)], axis=1)
    team_of = player_teams()
    weeks = pd.read_csv(DATA / "games.csv").set_index("gameId").week
    return {
        "grid": curve(KM_GRID), "league": curve(curves_off[LEAGUE]),
        "band": {"low": curve(teams.min(axis=1)), "high": curve(teams.max(axis=1))},
        "offense": team_records(off, "possessionTeam", curves_off),
        "defense": team_records(dfn, "defensiveTeam", curves_def),
        "rushers": records(out["rushers"].assign(team=lambda d: d.nflId.map(team_of))),
        "blockers": records(out["blockers"].assign(team=lambda d: d.nflId.map(team_of))),
        "kpi": kpis(plays, off, out["rushers"], out["blockers"], curves_off[LEAGUE]),
        "replays": [replay_record(g, p, title, weeks) for g, p, title in FEATURED_PLAYS],
    }


def render_page(payload):
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    replacements = {
        "__PLOTLY_URL__": f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js",
        "/*__CSS__*/": (WEB / "style.css").read_text(encoding="utf-8"),
        "/*__DATA__*/": data.replace("</", "<\\/"),  # pas de fin de <script> dans les données
        "/*__JS__*/": "\n".join((WEB / name).read_text(encoding="utf-8") for name in JS_FILES),
    }
    page = (WEB / "template.html").read_text(encoding="utf-8")
    for marker, content in replacements.items():
        if marker not in page:
            raise ValueError(f"Marqueur {marker} absent de {WEB / 'template.html'}")
        page = page.replace(marker, content)
    return page


def main():
    page = render_page(build_payload())
    DOCS.mkdir(exist_ok=True)
    (DOCS / "dashboard.html").write_text(page, encoding="utf-8")
    print("écrit :", DOCS / "dashboard.html", f"({len(page) / 1024:.0f} Ko)")


if __name__ == "__main__":
    main()
