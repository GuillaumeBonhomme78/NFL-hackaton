"""Analyse exploratoire des données Big Data Bowl (saison 2021, semaines 1-8)."""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data_nfl" / "data"
pd.set_option("display.width", 160, "display.max_columns", 30)


def section(title):
    print(f"\n{'=' * 10} {title} {'=' * 10}")


games = pd.read_csv(DATA / "games.csv")
plays = pd.read_csv(DATA / "plays.csv")
players = pd.read_csv(DATA / "players.csv")
pff = pd.read_csv(DATA / "pffScoutingData.csv")

section("Volumes")
print(f"games={len(games)}  plays={len(plays)}  players={len(players)}  pff rows={len(pff)}")
print("weeks:", sorted(games.week.unique()))

section("Plays : résultats et contexte")
print(plays.passResult.value_counts(dropna=False))
print(plays.pff_passCoverage.value_counts().head(10))
print(plays.pff_passCoverageType.value_counts())
print(plays.dropBackType.value_counts())
print("play action rate:", round(plays.pff_playAction.mean(), 3))
print(plays.offenseFormation.value_counts())
print("yards/play mean:", round(plays.playResult.mean(), 2))

section("PFF : rôles et pression")
print(pff.pff_role.value_counts())
pff["pressure"] = pff[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).sum(axis=1) > 0
play_pff = pff.groupby(["gameId", "playId"]).agg(
    pressure=("pressure", "any"),
    n_rush=("pff_role", lambda r: (r == "Pass Rush").sum()),
    n_block=("pff_role", lambda r: (r == "Pass Block").sum()),
).reset_index()
df = plays.merge(play_pff, on=["gameId", "playId"])
print("pressure rate:", round(df.pressure.mean(), 3))
print(df.n_rush.value_counts().sort_index())
df["blitz"] = df.n_rush >= 5
print("\nrésultat selon pression :")
print(df.groupby("pressure").agg(plays=("playId", "size"), yards=("playResult", "mean"),
                                 cmp=("passResult", lambda r: (r == "C").mean()),
                                 sack=("passResult", lambda r: (r == "S").mean()),
                                 int_=("passResult", lambda r: (r == "IN").mean())).round(3))
print("\nrésultat selon nb de rushers :")
print(df.groupby("n_rush").agg(plays=("playId", "size"), pressure=("pressure", "mean"),
                               yards=("playResult", "mean")).round(3))
print("\nmanques de couverture / résultat :")
print(df.groupby("pff_passCoverage").agg(plays=("playId", "size"), pressure=("pressure", "mean"),
                                         yards=("playResult", "mean")).round(2)
      .sort_values("plays", ascending=False).head(10))

section("Joueurs : top rushers / OL")
name = players.set_index("nflId").displayName
rush = pff[pff.pff_role == "Pass Rush"].groupby("nflId").agg(
    snaps=("playId", "size"), pressures=("pressure", "sum"), sacks=("pff_sack", "sum"))
rush["rate"] = rush.pressures / rush.snaps
rush["name"] = rush.index.map(name)
print(rush[rush.snaps >= 150].sort_values("rate", ascending=False).head(10).round(3))
blk = pff[pff.pff_role == "Pass Block"].copy()
blk["allowed"] = blk[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]].fillna(0).sum(axis=1) > 0
ol = blk.groupby("nflId").agg(snaps=("playId", "size"), allowed=("allowed", "sum"),
                              beaten=("pff_beatenByDefender", "sum"))
ol["rate"] = ol.allowed / ol.snaps
ol["name"] = ol.index.map(name)
print(ol[ol.snaps >= 250].sort_values("rate").head(5).round(3))
print(ol[ol.snaps >= 250].sort_values("rate").tail(5).round(3))
print("\nmatchups rusher/bloqueur renseignés:", blk.pff_nflIdBlockedPlayer.notna().sum())

section("Tracking")
cols = ["gameId", "playId", "nflId", "frameId", "team", "playDirection", "x", "y", "s", "a", "o", "dir", "event"]
trk = pd.concat((pd.read_csv(f, usecols=cols) for f in sorted((DATA / "tracking").glob("*.csv"))),
                ignore_index=True)
print(f"rows={len(trk):,}  plays={trk.groupby(['gameId', 'playId']).ngroups}")
print(trk.event.value_counts().head(15))
nframes = trk.groupby(["gameId", "playId"]).frameId.max()
print("frames/play :", nframes.describe().round(1).to_dict())

ev = trk[trk.event.isin(["ball_snap", "autoevent_ballsnap", "pass_forward", "autoevent_passforward",
                         "qb_sack", "qb_strip_sack", "run"])]
ev = ev.groupby(["gameId", "playId", "event"]).frameId.min().unstack()
snap = ev[["ball_snap", "autoevent_ballsnap"]].min(axis=1)
end = ev.reindex(columns=["pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"]).min(axis=1)
ttt = ((end - snap) / 10).rename("time_to_throw").dropna()
print("time snap -> pass/sack/run (s) :", ttt.describe().round(2).to_dict())
df = df.merge(ttt.reset_index(), on=["gameId", "playId"], how="left")
print("time_to_throw selon pression :", df.groupby("pressure").time_to_throw.median().round(2).to_dict())
df["ttt_bin"] = pd.cut(df.time_to_throw, [0, 2, 2.5, 3, 3.5, 4, 10])
print(df.groupby("ttt_bin", observed=True).agg(plays=("playId", "size"), pressure=("pressure", "mean"),
                                               sack=("passResult", lambda r: (r == "S").mean())).round(3))

# Distance QB <-> rusher le plus proche au fil du temps
roles = pff[["gameId", "playId", "nflId", "pff_role"]]
t = trk.merge(roles, on=["gameId", "playId", "nflId"], how="inner")
qb = t[t.pff_role == "Pass"][["gameId", "playId", "frameId", "x", "y"]]
rushers = t[t.pff_role == "Pass Rush"][["gameId", "playId", "frameId", "x", "y"]]
m = rushers.merge(qb, on=["gameId", "playId", "frameId"], suffixes=("", "_qb"))
m["d"] = np.hypot(m.x - m.x_qb, m.y - m.y_qb)
closest = m.groupby(["gameId", "playId", "frameId"]).d.min().reset_index()
closest = closest.merge(snap.rename("snap").reset_index(), on=["gameId", "playId"])
closest["t"] = (closest.frameId - closest.snap) / 10
min_d = closest[closest.t >= 0].groupby(["gameId", "playId"]).d.min().rename("min_rusher_dist")
df = df.merge(min_d.reset_index(), on=["gameId", "playId"], how="left")
print("\ndistance min rusher-QB (yd) selon pression :")
print(df.groupby("pressure").min_rusher_dist.describe().round(2))
curve = closest[(closest.t >= 0) & (closest.t <= 4)].merge(df[["gameId", "playId", "pressure"]])
curve["tb"] = (curve.t * 2).round() / 2
print("\ncourbe moyenne distance rusher-QB (yd) par 0.5s :")
print(curve.groupby(["tb", "pressure"]).d.mean().unstack().round(2))

section("Qualité des données")
print("plays sans snap tagué:", df.time_to_throw.isna().sum())
print("NA par colonne (plays):")
print(plays.isna().mean().sort_values(ascending=False).head(8).round(3))
