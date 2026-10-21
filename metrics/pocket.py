"""Pocket Clock : combien de temps la ligne offensive garde le QB à l'abri.

Une poche est "percée" dès qu'un pass rusher entre dans un rayon BREACH_RADIUS
autour du QB. On mesure le temps entre le snap et cette percée, censuré par la
passe : un QB qui lance à 2,1 s avec une poche intacte nous dit seulement que la
poche a tenu *au moins* 2,1 s. D'où un estimateur de Kaplan-Meier par équipe.

Sorties (dossier outputs/) :
- frames.parquet    : 1 ligne par (action, image) -> distance du rusher le plus proche, jauge de pression
- plays.csv         : 1 ligne par action -> temps de percée, rusher responsable, labels PFF
- teams_offense.csv : Pocket Clock par ligne offensive (+ yards, sacks)
- teams_defense.csv : idem côté pass rush
- rushers.csv       : percées par pass rusher
- blockers.csv      : percées concédées par bloqueur
"""
import numpy as np
import pandas as pd

from data import FPS, KEYS, OUT, load_tables, load_tracking, play_windows

BREACH_RADIUS = 2.0           # yards, choisi par validate_radius() contre les labels PFF
GAUGE_FAR, GAUGE_NEAR = 6.0, 1.0  # jauge 0 à 6 yd et plus, 1 à 1 yd et moins
MIN_RUSH_SNAPS, MIN_BLOCK_SNAPS = 150, 250
KM_GRID = np.round(np.arange(0, 6.01, 0.1), 1)  # instants (s) où l'on évalue la survie de la poche


def rusher_distances(trk, pff, win):
    """Distance de chaque rusher au QB, image par image, entre le snap et la fin de poche."""
    roles = pff[KEYS + ["nflId", "pff_role"]]
    t = trk.merge(roles, on=KEYS + ["nflId"])
    qb = t[t.pff_role == "Pass"][KEYS + ["frameId", "x", "y"]]
    rush = t[t.pff_role == "Pass Rush"][KEYS + ["frameId", "nflId", "x", "y", "s"]]
    d = rush.merge(qb, on=KEYS + ["frameId"], suffixes=("", "_qb")).merge(win, on=KEYS)
    d = d[(d.frameId >= d.snap_frame) & (d.frameId <= d.end_frame)]
    d["t"] = (d.frameId - d.snap_frame) / FPS
    d["dist"] = np.hypot(d.x - d.x_qb, d.y - d.y_qb)
    return d[KEYS + ["frameId", "t", "nflId", "dist", "s"]]


def frame_table(dist):
    idx = dist.groupby(KEYS + ["frameId"]).dist.idxmin()
    f = dist.loc[idx, KEYS + ["frameId", "t", "dist", "nflId"]]
    f = f.rename(columns={"dist": "closest_dist", "nflId": "closest_rusher"})
    f["pressure_gauge"] = ((GAUGE_FAR - f.closest_dist) / (GAUGE_FAR - GAUGE_NEAR)).clip(0, 1).round(3)
    f["breached"] = f.closest_dist < BREACH_RADIUS
    return f.sort_values(KEYS + ["frameId"]).reset_index(drop=True)


def breach_times(dist, radius):
    """Premier instant où chaque rusher entre dans le rayon (NaN s'il n'y entre jamais)."""
    inside = dist[dist.dist < radius]
    return inside.groupby(KEYS + ["nflId"]).t.min()


def play_table(dist, win, plays, pff, radius=BREACH_RADIUS):
    rb = breach_times(dist, radius).reset_index().sort_values("t")
    first = rb.groupby(KEYS).first().rename(columns={"t": "breach_time", "nflId": "breach_rusher"})
    p = win.merge(first.reset_index(), on=KEYS, how="left")
    p["breached"] = p.breach_time.notna()
    p["pocket_time"] = p.breach_time.fillna(p.time_to_throw)  # durée observée (censurée si pas de percée)

    pff = pff.assign(pressure=pff[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).sum(axis=1) > 0)
    per_play = pff.groupby(KEYS).agg(pff_pressure=("pressure", "any"),
                                     n_rushers=("pff_role", lambda r: (r == "Pass Rush").sum()))
    cols = KEYS + ["possessionTeam", "defensiveTeam", "passResult", "playResult", "down", "yardsToGo",
                   "pff_passCoverage", "pff_playAction", "dropBackType", "playDescription"]
    p = p.merge(per_play.reset_index(), on=KEYS).merge(plays[cols], on=KEYS)
    p["min_dist"] = p[KEYS].merge(dist.groupby(KEYS).dist.min().reset_index(), how="left").dist.values
    return p


def kaplan_meier(durations, events, grid):
    """Probabilité que la poche tienne encore à chaque instant de `grid`."""
    order = np.argsort(durations)
    d, e = np.asarray(durations)[order], np.asarray(events)[order]
    times = np.unique(d[e])
    at_risk = np.array([(d >= u).sum() for u in times])
    deaths = np.array([((d == u) & e).sum() for u in times])
    surv = np.cumprod(1 - deaths / at_risk)
    return np.array([surv[times <= g][-1] if (times <= g).any() else 1.0 for g in grid])


def km_summary(group):
    grid = KM_GRID
    s = kaplan_meier(group.pocket_time.values, group.breached.values, grid)
    below = grid[s < 0.5]
    return pd.Series({
        "plays": len(group),
        # médiane KM en secondes ; si la poche tient encore à 6 s dans plus de 50 % des cas, on note 6 (= "> 6 s")
        "pocket_clock": below[0] if len(below) else grid[-1],
        "pocket_clock_is_lower_bound": not len(below),
        "pocket_intact_2_5s": s[grid == 2.5][0],                # P(poche intacte à 2,5 s)
        "breach_rate": group.breached.mean(),
        "pff_pressure_rate": group.pff_pressure.mean(),
        "time_to_throw": group.time_to_throw.median(),
        "yards_per_play": group.playResult.mean(),
        "sack_rate": (group.passResult == "S").mean(),
    })


def team_table(p, team_col):
    t = p.groupby(team_col).apply(km_summary, include_groups=False)
    return t.sort_values("pocket_clock", ascending=team_col == "defensiveTeam").round(3)


def rusher_table(dist, p, pff, players):
    rb = breach_times(dist, BREACH_RADIUS).rename("breach_time").reset_index()
    rush = pff[pff.pff_role == "Pass Rush"][KEYS + ["nflId", "pff_hit", "pff_hurry", "pff_sack"]]
    rush = rush.merge(rb, on=KEYS + ["nflId"], how="left")
    rush["pressure"] = rush[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).sum(axis=1) > 0
    # vitesse de départ : vitesse moyenne sur les 0,5 premières secondes
    get_off = dist[dist.t <= 0.5].groupby(KEYS + ["nflId"]).s.mean().rename("get_off").reset_index()
    rush = rush.merge(get_off, on=KEYS + ["nflId"], how="left")
    first = p[KEYS + ["breach_rusher"]].rename(columns={"breach_rusher": "nflId"}).assign(first_in=1)
    rush = rush.merge(first, on=KEYS + ["nflId"], how="left").fillna({"first_in": 0})
    r = rush.groupby("nflId").agg(
        rush_snaps=("playId", "size"), breaches=("breach_time", "count"),
        first_in=("first_in", "sum"), median_breach_time=("breach_time", "median"),
        get_off=("get_off", "mean"), pff_pressures=("pressure", "sum"), sacks=("pff_sack", "sum"))
    r["breach_rate"] = r.breaches / r.rush_snaps
    r["pff_pressure_rate"] = r.pff_pressures / r.rush_snaps
    r = r.join(players.set_index("nflId")[["displayName", "officialPosition"]])
    r = r[r.rush_snaps >= MIN_RUSH_SNAPS]
    return r.sort_values("breach_rate", ascending=False).round(3)


def blocker_table(dist, pff, players):
    rb = breach_times(dist, BREACH_RADIUS).rename("breach_time").reset_index()
    blk = pff[pff.pff_role == "Pass Block"][KEYS + ["nflId", "pff_nflIdBlockedPlayer", "pff_sackAllowed",
                                                     "pff_hitAllowed", "pff_hurryAllowed"]]
    rb = rb.rename(columns={"nflId": "pff_nflIdBlockedPlayer"})
    blk = blk.merge(rb, on=KEYS + ["pff_nflIdBlockedPlayer"], how="left")
    blk["allowed"] = blk[["pff_sackAllowed", "pff_hitAllowed", "pff_hurryAllowed"]].fillna(0).sum(axis=1) > 0
    b = blk.groupby("nflId").agg(block_snaps=("playId", "size"), breaches_allowed=("breach_time", "count"),
                                 pff_allowed=("allowed", "sum"), sacks_allowed=("pff_sackAllowed", "sum"))
    b["breach_allowed_rate"] = b.breaches_allowed / b.block_snaps
    b["pff_allowed_rate"] = b.pff_allowed / b.block_snaps
    b = b.join(players.set_index("nflId")[["displayName", "officialPosition"]])
    b = b[b.block_snaps >= MIN_BLOCK_SNAPS]
    return b.sort_values("breach_allowed_rate").round(3)


def auc(score, label):
    """AUC (Mann-Whitney) : proba qu'une action sous pression ait un score plus élevé."""
    r = pd.Series(score).rank().values
    pos = np.asarray(label, bool)
    n1, n0 = pos.sum(), (~pos).sum()
    return (r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def validate_radius(dist, win, plays, pff):
    print("Validation du rayon de percée contre la pression PFF (hit/hurry/sack) :")
    for r in [1.0, 1.5, 2.0, 2.5, 3.0]:
        p = play_table(dist, win, plays, pff, r)
        y, yhat = p.pff_pressure, p.breached
        tpr, tnr = (yhat & y).sum() / y.sum(), (~yhat & ~y).sum() / (~y).sum()
        print(f"  r={r:.1f} yd  percée={yhat.mean():.2f}  pression PFF={y.mean():.2f}  "
              f"accord={(y == yhat).mean():.3f}  balanced acc={(tpr + tnr) / 2:.3f}")
    p = play_table(dist, win, plays, pff)
    print(f"  AUC distance min -> pression PFF : {auc(-p.min_dist.fillna(99), p.pff_pressure):.3f}")


def main():
    OUT.mkdir(exist_ok=True)
    tables = load_tables()
    plays, players, pff = tables["plays"], tables["players"], tables["pffScoutingData"]
    trk = load_tracking()
    win = play_windows(trk)
    dist = rusher_distances(trk, pff, win)

    validate_radius(dist, win, plays, pff)

    frame_table(dist).to_parquet(OUT / "frames.parquet", index=False)
    p = play_table(dist, win, plays, pff)
    p.to_csv(OUT / "plays.csv", index=False)
    off, dfn = team_table(p, "possessionTeam"), team_table(p, "defensiveTeam")
    off.to_csv(OUT / "teams_offense.csv")
    dfn.to_csv(OUT / "teams_defense.csv")
    rushers = rusher_table(dist, p, pff, players)
    rushers.to_csv(OUT / "rushers.csv")
    blockers = blocker_table(dist, pff, players)
    blockers.to_csv(OUT / "blockers.csv")

    print("\nPocket Clock global (médiane KM) :", km_summary(p).round(3).to_dict())
    print("\nLignes offensives (meilleures / pires) :")
    print(pd.concat([off.head(5), off.tail(5)]))
    print("\nCorrélations par équipe (offense) :")
    print(off[["pocket_clock", "pocket_intact_2_5s", "pff_pressure_rate", "yards_per_play", "sack_rate"]]
          .corr().round(2))
    print("\nPass rush (pocket clock le plus court = défense qui perce le plus vite) :")
    print(dfn.head(5))
    print("\nTop rushers (taux de percée) :")
    print(rushers.head(10)[["displayName", "rush_snaps", "breach_rate", "first_in", "median_breach_time",
                            "get_off", "pff_pressure_rate", "sacks"]])
    print("corr breach_rate / pff_pressure_rate :", round(rushers.breach_rate.corr(rushers.pff_pressure_rate), 2),
          " | get_off / pff_pressure_rate :", round(rushers.get_off.corr(rushers.pff_pressure_rate), 2))
    print("\nBloqueurs (moins / plus de percées concédées) :")
    print(pd.concat([blockers.head(5), blockers.tail(5)])[
        ["displayName", "officialPosition", "block_snaps", "breach_allowed_rate", "pff_allowed_rate"]])
    print("corr breach_allowed_rate / pff_allowed_rate :",
          round(blockers.breach_allowed_rate.corr(blockers.pff_allowed_rate), 2))


if __name__ == "__main__":
    main()
