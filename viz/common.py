"""Accès aux sorties du Pocket Clock (outputs/) pour les visualisations."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "metrics"))

from data import DATA, FPS, KEYS, OUT  # noqa: E402
from pocket import BREACH_RADIUS, KM_GRID, kaplan_meier  # noqa: E402

DOCS = ROOT / "docs"
LEAGUE = "NFL"
GOOD, BAD, NEUTRAL = "#2a9d8f", "#e63946", "#264653"


def load_outputs():
    names = ["plays", "teams_offense", "teams_defense", "rushers", "blockers"]
    missing = [n for n in names if not (OUT / f"{n}.csv").exists()]
    if missing:
        sys.exit(f"Fichiers absents dans outputs/ : {missing}. Lancer d'abord : python metrics/pocket.py")
    return {n: pd.read_csv(OUT / f"{n}.csv") for n in names}


def survival_curves(plays, team_col):
    """Courbe de Kaplan-Meier (P(poche intacte) en fonction du temps) par équipe + ligue entière."""
    curves = {team: kaplan_meier(g.pocket_time.values, g.breached.values, KM_GRID)
              for team, g in plays.groupby(team_col)}
    curves[LEAGUE] = kaplan_meier(plays.pocket_time.values, plays.breached.values, KM_GRID)
    return pd.DataFrame(curves, index=KM_GRID)


def spearman(a, b):
    """Corrélation de rangs : robuste au Pocket Clock censuré à 6 s (LA)."""
    return a.rank().corr(b.rank())
