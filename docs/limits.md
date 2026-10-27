---
description: "Ce que p2pwatch ne fait pas, et les conséquences pratiques des choix assumés."
---

# Limites connues

Ce que p2pwatch ne fait pas, et ce qui peut vous mordre. Rien ici n'est un bug : ce sont des choix
assumés, dont voici les conséquences pratiques.

## Le disque se remplit, et rien ne le vide

Les fichiers terminés restent dans `ed2k/downloads/incoming` indéfiniment. Aucun ménage automatique
n'existe, et il n'y en aura pas : p2pwatch n'ouvre jamais un fichier téléchargé, donc il ne peut
pas juger lequel garder.

Le crawler mesure l'espace libre et cesse d'accepter de nouveaux téléchargements quand il passerait
sous `download.min_free_bytes` (10 Gio par défaut). C'est un plancher qui vous protège d'un disque
plein, pas un plafond qui fait le ménage. Le tri reste à votre charge.

Effet secondaire sur un nœud ancien : la liste des fichiers partagés d'aMule est relue à chaque
cycle de téléchargement, et elle grossit avec chaque fichier terminé. Après des centaines de
téléchargements, attendez-vous à une détection de complétion plus lente.

## Une montée d'image demande de la place sur le disque, sur un gros catalogue

Au premier démarrage qui suit une mise à jour, le crawler applique les migrations de base en
attente. Il demande de la place sur deux disques :

- **Celui de `data/`.** Quand une migration en attente supprime ou réécrit des lignes, le crawler
  garde d'abord une [copie d'avant migration](operate.md#la-copie-davant-migration) de la base, à
  côté d'elle. Il lui faut la place de la copie (les pages utiles de la base, plus son `-wal`), puis
  celle de la migration (la base et son `-wal` encore), soit jusqu'à deux fois la base. Il la mesure
  avant d'écrire quoi que ce soit, et refuse de démarrer s'il en manque, en nommant la place
  nécessaire et la place libre (voir
  [« Un conteneur redémarre en boucle »](troubleshooting-start.md#un-conteneur-redémarre-en-boucle)).
  Pour un catalogue de 7,5 Go, comptez 15 Go libres.
- **Celui de Docker.** Une migration qui construit un index ou réécrit une table **trie dans des
  fichiers temporaires**, dans le dossier temporaire du conteneur : sur le disque où Docker range
  ses conteneurs, pas dans `data/`. Le crawler ne les compte pas dans sa mesure. S'il en manque, la
  migration échoue sans rien abîmer : elle est annulée, le catalogue reste dans son état d'avant,
  et le crawler refuse de démarrer. Le diagnostic et le remède sont dans
  [« Un conteneur redémarre en boucle »](troubleshooting-start.md#un-conteneur-redémarre-en-boucle).

### Le premier démarrage qui réécrit le catalogue

Les migrations `catalog/0006` à `0009` réécrivent tout le catalogue : chaque fichier change
d'identifiant, et les observations passent à un stockage compact. Mesuré le 2026-10-13 sur un
instantané du catalogue d'un nœud réel (5,9 Go), avec l'image, la base sur un dossier monté de
Docker Desktop et les limites de `compose.yml` (`--memory 2g`) :

| Étape | Durée | Mémoire au plus haut | En plus dans `data/` | Fichiers temporaires |
|---|---|---|---|---|
| Copie d'avant migration | 502,5 s | 11 Mo | la copie, 5,67 Go | aucun |
| `0006` à `0010` | 674,9 s, dont `0007` 445,6 s, `0008` 148,1 s et `0009` 79,0 s | 352 Mo | le WAL, 0,26 Go | 245 Mo au plus |

Comptez donc une vingtaine de minutes sur ce catalogue, davantage sur un plus gros, pendant
lesquelles le crawler ne cherche rien et l'interface web ne répond pas. Le journal annonce la copie
par `pre-migration copy of /data/catalog.db: writing ...`, puis chaque migration par une ligne comme
`migration 7: applying`. Ne redémarrez pas le conteneur avant la fin : une copie interrompue serait
supprimée puis refaite, une migration en cours annulée puis reprise à zéro.

Les migrations laissent d'abord le fichier à sa taille d'avant : l'espace libéré reste à
l'intérieur. `0009` le rend au disque (`VACUUM`) puis vide le WAL, et le fichier retombe à la taille
de ses données : 0,22 Go pour ce catalogue de 5,9 Go, à la version 10. La copie, elle, garde sa
taille jusqu'à ce que vous la supprimiez.

## Le durcissement des conteneurs s'arrête assez bas

Le crawler, `p2pwatch`, tourne directement sous votre `PUID:PGID`, avec `no-new-privileges:true`,
`pids_limit: 512` et `mem_limit: 2g`, et rien de plus. Pas de `read_only:` : une migration ou un
gros tri de SQLite écrit des fichiers temporaires, et le petit tmpfs qu'il faudrait a déjà manqué
une fois. Pas de `cap_drop: ALL` : il apporte peu à un processus qui tourne déjà sous votre
identifiant.

Le premier processus du conteneur `ed2k` tourne en root : il crée l'utilisateur `amule` à partir de
vos `PUID`/`PGID`, prend possession des dossiers montés et écrit la configuration d'aMule. Cela
exclut `user:`, `read_only:` et `cap_drop: ALL` ; chaque service abandonne ensuite ses privilèges de
lui-même. Ce qui reste, et que les fichiers compose doivent conserver : `no-new-privileges:true`,
`pids_limit: 512` et `mem_limit: 2g`.

**Risque accepté** : la compromission d'aMule, la pièce exposée aux pairs, atteint `ed2k/`, et
celle du crawler atteint `data/` (votre catalogue) et lit `ed2k/downloads/`. Une isolation plus
poussée (namespaces noyau, bac à sable) demanderait des privilèges ou des réglages système non
portables : c'est hors périmètre, délibérément. Ne « corrigez » pas ce point sans rouvrir la
décision, qui est documentée dans le dépôt.

## Quatre choses jamais éprouvées en conditions réelles

- **Le port-sync High-ID.** Il est construit et testé, et ses commandes s6 sont vérifiées sur un
  vrai conteneur, mais personne ne l'a encore vu obtenir un High-ID stable derrière un VPN à port
  forwarding, sur du vrai matériel. Le temps qu'amuled met à s'arrêter avant l'écriture du port
  n'est pas mesuré non plus : au-delà de 60 secondes, le port-sync renonce, relance amuled et
  réessaie après 5 minutes.
- **La variante VPN à deux conteneurs**, où le crawler joint aMule par le nom `ed2k`
  d'`ed2k-gluetun`. Seul son rendu par `docker compose config` est vérifié.
- **`no-new-privileges` combiné à l'abandon de privilèges** des services d'`ed2k`. La pile de smoke
  le vérifie en CI, sur amd64 et arm64, mais pas encore un nœud en production.
- **Les plafonds `mem_limit: 2g` et `pids_limit: 512`.** Chaque conteneur garde celui que le crawler
  et aMule partageaient dans un seul conteneur, sans mesure sur un nœud en production. Si un
  conteneur se fait tuer sans raison apparente, ce sont les deux premiers chiffres à regarder.

## Ce qui n'est pas prévu

Pas de serveur central, pas de découverte entre nœuds, pas de rétention ni de purge automatique du
catalogue. Le partage entre chercheurs se fait à la main, comme décrit sur
[la page d'accueil](index.md#partage).
