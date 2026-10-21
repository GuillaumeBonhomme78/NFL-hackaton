"""Graphiques statiques du Pocket Clock (docs/*.png), repris dans le README.

- pocket_survival.png : courbes de survie de la poche (meilleures / pires lignes offensives)
- teams.png           : Pocket Clock vs yards par action, comparé au taux de pression PFF
- rushers.png         : taux de percée vs taux de pression PFF des pass rushers
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import BAD, DOCS, GOOD, LEAGUE, NEUTRAL, load_outputs, spearman, survival_curves  # noqa: E402

N_HIGHLIGHT = 3
N_LABELLED_RUSHERS = 10
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "font.size": 10})


def median_time(curve):
    """Médiane KM lue sur la courbe, au même format que pocket_clock (« > 6 » si jamais sous 50 %)."""
    below = curve[curve < 0.5]
    return below.index[0] if len(below) else "> 6"


def plot_survival(plays, off):
    curves = survival_curves(plays, "possessionTeam")
    best, worst = off.possessionTeam.head(N_HIGHLIGHT), off.possessionTeam.tail(N_HIGHLIGHT)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for team in curves.columns.drop(LEAGUE):
        ax.step(curves.index, curves[team], where="post", color="0.85", lw=0.8, zorder=1)
    for teams, color in [(best, GOOD), (worst, BAD)]:
        for team in teams:
            ax.step(curves.index, curves[team], where="post", color=color, lw=2,
                    label=f"{team}  ({median_time(curves[team])} s)", zorder=3)
    ax.step(curves.index, curves[LEAGUE], where="post", color=NEUTRAL, lw=2.5, ls="--",
            label=f"Ligue  ({median_time(curves[LEAGUE])} s)", zorder=4)
    ax.axhline(0.5, color="0.4", lw=0.8)
    ax.text(0.05, 0.47, "Pocket Clock = passage sous 50 %", fontsize=8, color="0.3")
    ax.set(xlim=(0, 6), ylim=(0, 1.02), xlabel="Temps depuis le snap (s)",
           ylabel="P(aucun rusher à moins de 2 yd du QB)",
           title="Combien de temps la poche tient-elle ? (Kaplan-Meier, semaines 1 à 8 de 2021)")
    ax.legend(title="Lignes offensives (Pocket Clock)", fontsize=8, title_fontsize=8, loc="lower left")
    return fig


def plot_teams(off):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    panels = [("pocket_clock", "Pocket Clock (s) ; LA = « > 6 s »", GOOD),
              ("pff_pressure_rate", "Taux de pression PFF (hit, hurry, sack)", BAD)]
    for ax, (col, xlabel, color) in zip(axes, panels):
        ax.scatter(off[col], off.yards_per_play, color=color, s=28, alpha=0.8)
        for _, row in off.iterrows():
            ax.annotate(row.possessionTeam, (row[col], row.yards_per_play), fontsize=7,
                        xytext=(3, 2), textcoords="offset points")
        rho = spearman(off[col], off.yards_per_play)
        ax.set(xlabel=xlabel, title=f"Spearman ρ = {rho:+.2f}")
    axes[0].set_ylabel("Yards par action de passe")
    fig.suptitle("Le temps offert au QB se retrouve dans les yards (32 lignes offensives)", fontweight="bold")
    fig.tight_layout()
    return fig


def plot_rushers(rushers):
    fig, ax = plt.subplots(figsize=(8, 5.2))
    sc = ax.scatter(rushers.pff_pressure_rate, rushers.breach_rate, c=rushers.median_breach_time,
                    cmap="viridis_r", s=rushers.rush_snaps / 4, alpha=0.85, edgecolor="white", lw=0.5)
    for _, row in rushers.nlargest(N_LABELLED_RUSHERS, "breach_rate").iterrows():
        ax.annotate(row.displayName, (row.pff_pressure_rate, row.breach_rate), fontsize=7,
                    xytext=(4, 2), textcoords="offset points")
    rho = rushers.breach_rate.corr(rushers.pff_pressure_rate)
    ax.set_xlim(right=rushers.pff_pressure_rate.max() + 0.035)  # place pour les noms à droite
    ax.set(xlabel="Taux de pression PFF (noté à la main)", ylabel="Taux de percée (mesuré par tracking)",
           title=f"Pass rushers (150 snaps ou plus) : le tracking retrouve le jugement PFF (r = {rho:.2f})")
    fig.colorbar(sc, ax=ax, label="Temps médian de percée (s)")
    return fig


def main():
    DOCS.mkdir(exist_ok=True)
    out = load_outputs()
    figures = {"pocket_survival.png": plot_survival(out["plays"], out["teams_offense"]),
               "teams.png": plot_teams(out["teams_offense"]),
               "rushers.png": plot_rushers(out["rushers"])}
    for name, fig in figures.items():
        fig.savefig(DOCS / name, bbox_inches="tight")
        plt.close(fig)
        print("écrit :", DOCS / name)


if __name__ == "__main__":
    main()
