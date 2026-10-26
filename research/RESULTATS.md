# Étude des variantes ORB (26 octobre 2026)

Script : `research/orb_variants.py`. Données : bougies de 5 minutes Yahoo Finance,
du 31 juillet au 23 octobre 2026 (60 séances), sur 15 actions américaines :
SPY, QQQ, TSLA, NVDA, AAPL, AMD, META, AMZN, MSFT, GOOGL, NFLX, AVGO, MU, PLTR, COIN.
Résultats en R (multiples du risque au stop), après 0,01 $ par action à l'achat et à la vente.
Les 40 premières séances classent les variantes, les 20 dernières (à partir du
28 septembre) servent de contrôle. 160 variantes testées.

## La règle du skill telle quelle

| | trades | gagnants | R moyen | facteur de profit |
| --- | --- | --- | --- | --- |
| 40 premières séances | 333 | 48,9 % | -0,011 | 0,97 |
| 20 dernières séances | 167 | 46,7 % | -0,050 | 0,89 |

Positive sur 5 actions sur 15. **Aucun avantage : légèrement perdante après frais.**

## Ce que montre l'étude

- **Les meilleures variantes sur la première période échouent sur la seconde.**
  La meilleure (filtre « gap », sortie à la clôture, entrées avant 11:00) passe de
  +0,23 R à -0,22 R. C'est le piège classique de l'optimisation : on trouve ce qui a
  marché par hasard.
- Seules 17 variantes sur 128 sont positives sur les deux périodes, ce qui n'est pas
  plus que le hasard.
- Le filtre de volume dégrade le résultat. Le filtre VWAP ne filtre rien (une clôture
  au-dessus du range est presque toujours au-dessus du VWAP).
- **Deux pistes reviennent de façon cohérente** : ne prendre le signal que si SPY monte
  depuis l'ouverture, et ne plus entrer après 11:00. La meilleure combinaison
  (range 15 min, stop au milieu, objectif 1,5R, entrées avant 11:00, filtre SPY) :
  271 trades, +0,09 R par trade, +0,06 R puis +0,15 R sur les deux périodes, positive
  sur 11 actions sur 15.

## Ce que ça vaut

Pas grand-chose encore : +0,09 R avec 271 trades, c'est environ 1,3 erreur-type au-dessus
de zéro, sur 60 séances d'un seul régime de marché, et choisi parmi 160 variantes. Ce
n'est **pas** un avantage démontré. C'est une piste à suivre en démo, sans argent réel,
en comptant les trades jusqu'à en avoir plusieurs centaines.

Dans les scripts TradingView, cette piste correspond à : « Pas d'entrée après » = 11:00,
« Objectif » = 1,5, « Filtre marché » coché. Ce n'est pas un conseil financier.
