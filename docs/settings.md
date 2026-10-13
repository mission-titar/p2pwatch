---
description: "Les réglages courants d'un nœud en route : cataloguer sans télécharger, changer un port, brancher la supervision."
---

# Régler le nœud

Les réglages que vous êtes le plus susceptible de vouloir changer une fois le nœud en route : ne
rien télécharger, déplacer un port, brancher votre supervision.

## Cataloguer sans télécharger

Par défaut, un nœud télécharge les candidats qu'il identifie avec certitude. Pour seulement
cataloguer et être notifié, sans qu'aucun fichier n'atterrisse sur votre disque :

1. Dans `crawler.yml`, passez `download.enabled` de `true` à `false`.
2. Relancez depuis votre dossier de travail :

   ```bash
   docker compose up -d
   ```

Rien d'autre ne change. Les mêmes conteneurs démarrent, le catalogue web est servi pareil et les
notifications partent toujours. Seule la boucle de téléchargement n'est pas câblée, donc
`ed2k/downloads/incoming` reste vide.

C'est un simple réglage, pas une autre façon de monter le nœud : il n'y a aucun profil compose à
ajouter ni à retirer.

## Changer un port

Les ports ne sont pas des variables : ils sont écrits en clair dans les sections `ports:` des
fichiers compose. Le `8080`, le catalogue, est dans `compose.yml`. Le `4711`, l'interface d'aMule,
est dans `ed2k/direct.compose.yml`, avec les ports eD2k et Kad, ou dans `ed2k/vpn.compose.yml` si
vous êtes derrière un VPN (il y est publié par le service `ed2k-gluetun`).

Ne changez que **le nombre de gauche**, celui côté hôte : `"8090:8080"` publie le catalogue sur
8090. Dans le conteneur, les ports sont figés.

Si un port est déjà pris au lancement, voyez
[« Le port est déjà pris »](troubleshooting-start.md#le-port-est-déjà-pris).

## Derrière un reverse proxy

Si vous mettez un proxy devant le port 8080, réglez `webui.amule_url` dans `crawler.yml` sur
l'adresse à laquelle **le navigateur** peut joindre l'interface d'aMule. Cette clé n'est que la
cible du lien « aMule » de la navigation, et c'est le navigateur, pas le conteneur, qui la résout :
sa valeur par défaut, `http://localhost:4711`, ne veut rien dire pour un visiteur distant.

L'exemple de configuration complet est dans
[Faire tourner un nœud](operate.md#exposition-derrière-un-reverse-proxy).

## Métriques Prometheus

Le crawler expose un point d'accès Prometheus sur le port réglé par `observability.metrics.port`
dans `crawler.yml` (`9090` par défaut, actif par défaut). **Ni Prometheus ni Grafana ne sont livrés
avec la pile** : si vous voulez des tableaux de bord, faites pointer votre propre Prometheus sur le
nœud.

Ce port n'est pas publié sur l'hôte. Pour le joindre, publiez-le vous-même en ajoutant
`"9090:9090"` à la liste `ports:` du service `p2pwatch` dans `compose.yml`, sous les deux
variantes : le crawler n'est jamais derrière le VPN.

Traitez ce port comme le 8080 : **aucune authentification**, donc gardez-le hors de l'Internet
ouvert.

Exemple de `scrape_config` pour votre propre `prometheus.yml` :

```yaml
scrape_configs:
  - job_name: 'p2pwatch'
    static_configs:
      - targets: ['node.example.lan:9090']   # l'hôte sur lequel vous avez publié 9090
```

Pour couper entièrement le point d'accès, mettez `observability.metrics.enabled: false` dans
`crawler.yml`. Le crawl et le catalogue web continuent normalement.

## Le seuil des sources de nouveau utiles

`download.reappeared_after_seconds` (`43200` par défaut, soit 12 h) règle l'alerte `reappeared`
([Historique des sources](operate.md#historique-des-sources)) : une source de nouveau utile
n'alerte que si le nœud n'a rien appris de ce qu'elle détient pendant plus de ce nombre de
secondes. Plus court, une source qui revient chaque soir alerte plus souvent ; plus long, seules les
longues absences alertent.

La clé accepte tout nombre positif, décimales comprises, mais une valeur sous l'heure (`3600`) a
peu de sens : aMule ne réinterroge une source en attente que toutes les 15 minutes, et une source
peut quitter sa liste puis y revenir sans s'être absentée. Une valeur nulle, négative, infinie,
`.nan` ou supérieure à 30 jours (`2592000`) est refusée au démarrage, avec un message qui nomme la
clé ([Les bornes des durées](#les-bornes-des-durées)). La valeur est lue au démarrage :
relancez le crawler (`docker compose restart p2pwatch`) après l'avoir changée.

## La fréquence de relevé des sources

`download.sources_interval_seconds` (`300` par défaut, soit 5 minutes) règle tous les combien le
crawler relève les sources de ses téléchargements
([Historique des sources](operate.md#historique-des-sources)). Le relevé a lieu au premier tour de
la boucle de téléchargement qui suit cet intervalle : deux relevés sont donc espacés de l'intervalle,
plus un tour de la boucle au plus (`download.poll_interval_seconds` et la durée du cycle).

Chaque relevé ajoute au catalogue un point par source : à 5 minutes, de l'ordre de 0,13 Go par an
pour une cinquantaine de sources (estimation du 2026-10-13). Plus court, l'historique est plus fin
et les alertes `new-source` et `reappeared` partent plus tôt, mais le catalogue grossit d'autant et
le crawler interroge amuleapi plus souvent. Plus long, une source restée moins longtemps que
l'intervalle peut passer inaperçue. Si vous le changez, ajustez aussi
[l'écart qui coupe une période](#lécart-qui-coupe-une-période-de-source).

Une valeur nulle, négative, infinie, `.nan` ou supérieure à un jour (`86400`) est refusée au
démarrage, avec un message qui nomme la clé ([Les bornes des durées](#les-bornes-des-durées)). La valeur est lue au démarrage : relancez le crawler
après l'avoir changée.

## L'écart qui coupe une période de source

`webui.source_period_gap_seconds` (`990` par défaut) règle l'affichage de l'historique des sources
dans le catalogue web : deux points d'une même source plus éloignés que ce nombre de secondes ouvrent
une nouvelle période. 990, c'est 3 x (300 + 30), trois écarts entre relevés aux réglages par défaut,
pour qu'une lecture manquée ne coupe pas une période. Si vous changez
`download.sources_interval_seconds` ou `download.poll_interval_seconds`, gardez-le à
3 x (`sources_interval_seconds` + `poll_interval_seconds`).

Il ne change que l'affichage : le catalogue garde ses points, et rien n'est réécrit. Un catalogue
fusionné est coupé par l'écart du nœud qui l'affiche : les points d'un nœud qui relève plus rarement
y apparaissent en périodes d'un seul point, et augmenter l'écart les réunit. La clé vaut aussi sur un
nœud qui ne télécharge pas, puisqu'il peut afficher un catalogue fusionné.

Une valeur nulle, négative, infinie, `.nan` ou supérieure à un jour (`86400`) est refusée au
démarrage, avec un message qui nomme la clé ([Les bornes des durées](#les-bornes-des-durées)). La valeur est lue au démarrage : relancez le crawler
après l'avoir changée.

## Les bornes des durées

Chaque durée de `crawler.yml` est un nombre de secondes strictement positif et fini, et borné : un
jour pour un délai, 30 jours pour une absence. Au-delà, le crawler refuse de démarrer, avec un
message qui nomme la clé et sa borne.

| Clé | Borne |
|---|---|
| `shutdown_deadline_seconds` | 1 jour (`86400`) |
| `backoff.base_seconds`, `backoff.cap_seconds` | 1 jour (`86400`) |
| `observability.notification_timeout_seconds` | 1 jour (`86400`) |
| `download.poll_interval_seconds` | 1 jour (`86400`) |
| `download.sources_interval_seconds` | 1 jour (`86400`) |
| `webui.source_period_gap_seconds` | 1 jour (`86400`) |
| `download.lost_after_seconds` | 30 jours (`2592000`) |
| `download.reappeared_after_seconds` | 30 jours (`2592000`) |
