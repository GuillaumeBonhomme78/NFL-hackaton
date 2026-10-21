"""Chargement des données Big Data Bowl et repères temporels de chaque action."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data_nfl" / "data"
OUT = ROOT / "outputs"

KEYS = ["gameId", "playId"]
SNAP_EVENTS = ["ball_snap", "autoevent_ballsnap"]
END_EVENTS = ["pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"]
FPS = 10


def load_tables():
    return {name: pd.read_csv(DATA / f"{name}.csv")
            for name in ["games", "plays", "players", "pffScoutingData"]}


def load_tracking(cols=("gameId", "playId", "nflId", "frameId", "x", "y", "s", "a", "event")):
    files = sorted((DATA / "tracking").glob("*.csv"))
    return pd.concat((pd.read_csv(f, usecols=list(cols)) for f in files), ignore_index=True)


def play_windows(tracking):
    """Frame du snap et de fin de poche (passe, sack ou scramble) pour chaque action."""
    ev = tracking.dropna(subset=["event"]).groupby(KEYS + ["event"]).frameId.min().unstack()
    snap = ev.reindex(columns=SNAP_EVENTS).min(axis=1)
    end = ev.reindex(columns=END_EVENTS).min(axis=1)
    last = tracking.groupby(KEYS).frameId.max()
    win = pd.DataFrame({"snap_frame": snap, "end_frame": end}).reindex(last.index)
    win["end_frame"] = win.end_frame.fillna(last)
    win = win.dropna(subset=["snap_frame"])
    win = win[win.end_frame > win.snap_frame]
    win["time_to_throw"] = (win.end_frame - win.snap_frame) / FPS
    return win.reset_index()
