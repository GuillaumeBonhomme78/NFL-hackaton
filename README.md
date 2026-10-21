# NFL Big Data Bowl : quête du jour

> **Résumé (à finaliser avant le rendu, 3 à 5 phrases)**
> _Ce qu'on a construit :_ TODO
> _Ce que ça révèle :_ TODO
> _Qui l'utiliserait :_ TODO (coach de ligne offensive / défensive, recruteur, commentateur)

## Le défi

Construire un outil ou une visualisation de données NFL qu'un **coach**, un **recruteur** ou un **commentateur** utiliserait, sous l'une de ces deux formes :

- **Visualisation / outil de comparaison** : graphique, dashboard, animation ou outil interactif ;
- **Métrique / score** : une nouvelle statistique qui mesure quelque chose d'encore inexploré.

Évaluation (note de 1 à 5) : compréhension du football, exécution technique, communication, originalité.

## Les données

Source : [ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data](https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data) (format du Big Data Bowl 2023, NGS + PFF).

- **Périmètre** : saison 2021, semaines 1 à 8, 122 matchs, environ 8 500 actions de passe, environ 8,3 M lignes de tracking.
- **Tracking** (`tracking_[gameId].csv`) : position `x`/`y`, vitesse `s`, accélération `a`, orientation `o` et direction `dir` de chaque joueur et du ballon, à 10 images/s, du snap jusqu'à la passe ou au sack.
- **Plays** (`plays.csv`) : contexte de l'action (down, distance, formation, personnel, couverture PFF, résultat).
- **PFF Scouting** (`pffScoutingData.csv`) : rôle de chaque joueur (pass rush, pass block, coverage, route), hits, hurries et sacks, sacks concédés, adversaire bloqué, type de bloc.
- **Players / Games** : infos joueurs (poste, taille, poids) et matchs.

Clés de jointure : `gameId`, `playId`, `nflId`.

## Installation

```bash
git clone https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data.git data_nfl   # environ 1 Go, non versionné
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## La métrique : Pocket Clock

La poche est **percée** dès qu'un pass rusher entre à moins de **2 yards** du QB. Le **Pocket Clock** d'une ligne offensive, c'est le temps médian avant cette percée.

- **Censure** : quand le QB lance avant la percée, on sait seulement que la poche a tenu *au moins* jusque-là. Le temps médian est donc estimé avec Kaplan-Meier (méthode d'analyse de survie), pas avec une simple moyenne.
- **Validation contre PFF** (hit, hurry, sack, notés à la main) : 82 % d'accord action par action, et un AUC de 0,88 pour la distance minimale entre un rusher et le QB. Le rayon de 2 yd est celui qui maximise l'accord : on a testé de 1 à 3 yd.
- **Joueurs** : le taux de percée des rushers corrèle à 0,81 avec leur taux de pression PFF. Pour les bloqueurs, le duel est identifié via `pff_nflIdBlockedPlayer` et la corrélation est de 0,67.

## Structure du projet

```
analysis/explore.py   analyse exploratoire (stats descriptives, pression, temps de lancer)
metrics/data.py       chargement des CSV + fenêtre snap -> passe/sack de chaque action
metrics/pocket.py     calcul du Pocket Clock et génération de outputs/
outputs/              résultats consommés par les visualisations
```

## Utilisation

```bash
python metrics/pocket.py      # environ 20 s, régénère outputs/
```

### Fichiers de sortie (`outputs/`)

| Fichier | Grain | Colonnes clés |
|---|---|---|
| `frames.parquet` | action × image (snap -> passe) | `t` (s depuis le snap), `closest_dist` (yd), `closest_rusher` (nflId), `pressure_gauge` (0 à 1), `breached` |
| `plays.csv` | action | `pocket_time`, `breached`, `breach_time`, `breach_rusher`, `time_to_throw`, `pff_pressure`, `min_dist`, contexte (équipes, résultat, couverture…) |
| `teams_offense.csv` | ligne offensive | `pocket_clock` (s ; 6 = « plus de 6 s »), `pocket_intact_2_5s`, `breach_rate`, `yards_per_play`, `sack_rate` |
| `teams_defense.csv` | pass rush d'une équipe | mêmes colonnes, vues côté défense |
| `rushers.csv` | pass rusher (150 snaps ou plus) | `breach_rate`, `first_in`, `median_breach_time`, `get_off` (vitesse moyenne sur 0,5 s, yd/s), `pff_pressure_rate` |
| `blockers.csv` | bloqueur (250 snaps ou plus) | `breach_allowed_rate`, `pff_allowed_rate`, `sacks_allowed` |

Jointure avec le tracking brut : `gameId`, `playId`, `frameId`.

## Équipe

- Guillaume Bonhomme
