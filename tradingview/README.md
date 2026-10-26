# La stratégie ORB du skill, sur TradingView

Deux scripts Pine (version 6) qui appliquent exactement les règles des skills
`/trader-entry`, `/trader-exit` et `/trader-budget` :

| fichier | type | pour quoi faire |
| --- | --- | --- |
| `orb_strategy.pine` | stratégie | backtester les règles sur l'historique (onglet Strategy Tester) |
| `orb_indicator.pine` | indicateur | suivre la séance en direct et recevoir des alertes |

## Les règles

1. **Range d'ouverture** : plus haut et plus bas de 9:30 à 9:45, heure de New York.
2. **Entrée** : la première bougie de 5 minutes *terminée* qui *clôture* au-dessus du
   haut du range (une mèche ne compte pas), si elle clôture entre 09:45 et 15:30.
3. **Stop** : milieu du range, arrondi au centime vers le bas. Refusé si le risque est
   sous 0,05 % du prix.
4. **Objectif** : 1R (entrée + une fois le risque).
5. **À plat à 15:55** New York, gagnant ou perdant.
6. **Taille** : perte max par trade (50 $) / risque par action, arrondi vers le bas,
   et pas plus de 4 000 $ par ordre.
7. Long uniquement, un seul trade par jour et par symbole.

Tout se règle dans les paramètres du script.

## Installer

1. TradingView, en bas : **Éditeur Pine**. Nouveau script, tout effacer, coller le
   contenu du fichier, **Enregistrer**, puis **Ajouter au graphique**.
2. Graphique en **5 minutes**, séance régulière (pas les heures étendues).
3. Pour les alertes de l'indicateur : **Alerte**, condition « ORB Day Trader
   (signaux) », puis **Tout appel de fonction alert()** pour le message complet
   (quantité, stop, objectif, perte max).

## Vérifié

Une traduction Python ligne à ligne de l'indicateur, sur les données TSLA du dépôt :

- 19 octobre 2026 : signal à 10:15, 8 actions à 364,18, stop 358,32, objectif 370,04,
  perte max 46,88 $ (les mêmes chiffres que le skill) ;
- 59 séances précédentes : 33 signaux, 13 objectifs, 15 stops, 5 sorties à 15:55
  (le même décompte que `/trader-timemachine`).

Les scripts ne passent aucun ordre. Les ordres passent par `/trader-broker`, avec
votre « oui ». Ce n'est pas un conseil financier.
