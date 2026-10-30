---
description: "Migrer un nœud 4.x vers la 5.0 : aMule passe dans son propre conteneur, et ses dossiers sous ed2k/."
---

# Migrer un nœud 4.x vers la 5.0

La 5.0 renomme mulewatch en **p2pwatch** et sépare le nœud en deux conteneurs : `p2pwatch`, le
crawler et son catalogue web, et `ed2k`, le client eMule avec son port-sync. Les dossiers d'aMule
passent sous `ed2k/`, et une ligne de `compose.yml` choisit entre la variante directe et la
variante VPN. Aucune donnée n'est perdue. Six étapes, depuis votre dossier de travail.

!!! warning "Sauvegardez d'abord votre configuration et votre catalogue"

    Le premier démarrage de la 5.0 réécrit les deux bases. Il en garde d'abord une
    [copie d'avant migration](operate.md#la-copie-davant-migration) dans `data/`, mais votre
    sauvegarde reste le retour le plus sûr vers la 4.x : elle garde aussi votre configuration. Les
    deux demandent de la place : la sauvegarde la taille de `data/`, le premier démarrage jusqu'à
    deux fois le catalogue dans `data/`. `amule/` et `downloads/` ne sont que déplacés, inutile de
    les copier.

    ```bash
    mkdir ../mulewatch.4x.bak
    cp -a .env *.yml data ../mulewatch.4x.bak/
    ```

**1. Arrêtez le nœud 4.x**, avec ses anciens fichiers compose.

```bash
docker compose down     # ou -f gluetun.compose.yml si vous étiez sur la pile VPN
```

**2. Rangez les dossiers d'aMule sous `ed2k/`.** Un déplacement sur le même disque, immédiat quelle
que soit la taille de `downloads/`. `data/` ne bouge pas.

```bash
mkdir ed2k
mv amule downloads ed2k/
```

**3. Éditez `crawler.yml` et `matcher.yml`.** Dans `crawler.yml`, retirez la section `port_sync:`
entière, et ces six clés de la racine : `cycle_interval_seconds`, `decision_poll_interval_seconds`,
`search_poll_budget_seconds`, `search_poll_interval_seconds`, `keyword_pause_min_seconds` et
`keyword_pause_max_seconds`. Tant que l'une reste, le crawler refuse de démarrer en la nommant :
`port_sync: was removed, delete it from crawler.yml`.

Retirez aussi `enabled` de la section `webui:`, et la clé `metrics` de la section
`observability:` : le catalogue web est toujours servi, et les métriques passent sur son port.
Restées, elles sont refusées de même : `webui.enabled: was removed, delete it from crawler.yml` et
`observability.metrics: was removed, delete it from crawler.yml`.

Déplacez ensuite la section `backoff:` sous `search:`, à côté de `keywords`, que la 5.0 rend
obligatoire. Laissée à la racine, elle est refusée de même :
`backoff: moved to 'search.backoff', move it in crawler.yml`.

```yaml
search:
  keywords: [keroro, titar]
  backoff:
    base_seconds: 2.0
    cap_seconds: 300.0
    factor: 2.0
    jitter_ratio: 0.3
```

Dans chaque cible de `observability.notifications`, renommez enfin la clé `tag` en `audience`, sans
changer sa valeur. Laissée telle quelle, elle est refusée en nommant la nouvelle :
`observability.notifications[0]: key 'tag' was renamed 'audience', rename it in crawler.yml`.

```yaml
observability:
  notifications:
    - url: "discord://${DISCORD_WEBHOOK_ID}/${DISCORD_WEBHOOK_TOKEN}"
      audience: operations
```

Dans `matcher.yml`, `min` et `fuzz` deviennent `min_coverage` et `min_similarity`, sur un token
`coverage` comme sur une référence `{ token: … }`, et le paramètre `{segment}` des regex devient
`{letter}`. Dans la politique livrée, cela touche deux lignes : la regex de `segment_id` finit par
`\\s*{letter}`, et `title_hit` s'écrit ainsi. Un ancien nom est refusé en nommant le nouveau :
`token 'title_hit': key 'min' was renamed 'min_coverage', rename it in matcher.yml`.

```yaml
tokens:
  title_hit:     { coverage: title, min_coverage: 0.6 }
```

Si vous avez ajouté un token `attr_between`, ses attributs `size_mb` et `duration_sec` deviennent
`size_mib` et `duration_seconds`. Ses bornes `min` et `max` ne changent pas.

**4. Remplacez les fichiers compose** par ceux du dossier `deploy` de la 5.0 : `compose.yml` à la
racine, et les trois fichiers de son dossier `ed2k/` dans le vôtre.

```bash
rm compose.yml base.compose.yml gluetun.compose.yml
cp /chemin/vers/deploy-5.0/compose.yml .
cp /chemin/vers/deploy-5.0/ed2k/*.compose.yml ed2k/
```

Sur la pile VPN, remplacez dans `compose.yml` la ligne `- ed2k/direct.compose.yml` par
`- ed2k/vpn.compose.yml`. Plus de `-f` ensuite : les mêmes commandes servent les deux variantes. Si
vous aviez changé un port, reportez-le : le 8080 est dans `compose.yml`, les ports d'aMule dans
`ed2k/direct.compose.yml` (le 4711 seul dans `ed2k/vpn.compose.yml`).

**5. Réglez `VPN_PORT_FORWARDING` dans `.env`** (variante VPN seulement). C'est désormais le seul
interrupteur du port-sync : si `port_sync.enabled` valait `true`, mettez `on`, sinon laissez `off`.
Si vous aviez changé `gluetun_control_url` ou l'un des deux intervalles, leurs variables sont dans
[Devenir High-ID](high-id.md#route-a-recommandée--le-port-forwarding-de-votre-vpn).

**6. Démarrez.**

```bash
docker compose up -d
docker compose ps       # p2pwatch Up, ed2k Up (healthy) en ~30 s, plus ed2k-gluetun sous VPN
```

Un nœud direct dont la box redirige ses ports redirige désormais `4672/udp` (Kad), et non plus
`4662/udp`. `4662/tcp` ne change pas.

## Ce qui change

- **Le premier démarrage copie puis réécrit les deux bases** : il garde
  `data/catalog.db.pre-0006.<heure>_UTC` et `data/local.db.pre-0006.<heure>_UTC`, puis migre. Une
  vingtaine de minutes sur un catalogue de 6 Go, dont huit pour la copie, pendant lesquelles le
  catalogue web ne répond pas. Ne redémarrez rien avant la fin, voir
  [Limites connues](limits.md#le-premier-démarrage-qui-réécrit-le-catalogue). Faute de place dans
  `data/`, le crawler refuse de démarrer sans rien écrire, voir
  [Le déploiement bloque](troubleshooting-start.md#un-conteneur-redémarre-en-boucle).
- **Deux journaux.** `docker compose logs p2pwatch` ne montre plus que le crawler ; amuled et le
  port-sync écrivent dans `docker compose logs ed2k`, amuleapi dans `ed2k/amule/amuleapi.log`.
- **Sous la variante VPN, le crawler sort du tunnel.** Seul `ed2k` passe par `ed2k-gluetun`. Le
  crawler ne parle à aucun pair, et vos notifications partent de l'adresse de votre machine.
- **Le crawler joint amuleapi en direct**, sans plus suivre `HTTP_PROXY` ni `NO_PROXY` : un proxy
  donné au conteneur `p2pwatch` ne s'applique plus à cette connexion.
- **Une configuration invalide fait redémarrer `p2pwatch` en boucle** (`Restarting`) au lieu
  d'arrêter le conteneur. L'erreur est dans `docker compose logs p2pwatch`.
- **`${NOM}` est résolu dans toute valeur texte de `crawler.yml`**, et non plus seulement dans
  `amule_api_password`, les deux chemins de base, `webui.amule_url` et les cibles de notification.
  Une variable absente de l'environnement est refusée où qu'elle soit, même dans une section
  désactivée, en nommant sa clé : `search.keywords[0]: environment variable 'X' referenced but not
  set`. Une valeur résolue reste du texte : un nombre ne peut pas venir de l'environnement.
- **La clé `node_id` de `crawler.yml`, jamais documentée, est refusée** (`node_id: was removed,
  ...`) : l'identifiant du nœud est toujours celui que `local.db` garde.
- **Les métriques `emule_*` deviennent `p2pwatch_*`.** Les trois du port-sync
  (`emule_port_sync_triggered`, `emule_port_mismatch`, `emule_high_id_recovered`) disparaissent
  avec leurs notifications : un Low-ID se lit sur `p2pwatch_channel_connectable`, et un canal non
  joignable depuis 5 minutes est notifié.
- **Le label `network` devient `channel`** sur `p2pwatch_searches`, `p2pwatch_observations` et
  `p2pwatch_search_failures`, qui gagnent aussi un label `client`. Adaptez les requêtes de vos
  tableaux de bord et de vos règles d'alerte.
- **Prometheus scrape le 8080.** `/metrics` est une route du catalogue web,
  `http://<nœud>:8080/metrics`, et plus rien n'écoute sur le 9090 : visez `:8080` dans votre
  `scrape_config`, et retirez `"9090:9090"` des `ports:` si vous l'aviez publié. Le format passe
  d'OpenMetrics 1.0.0 au texte 0.0.4 : les séries gardent leurs noms, leurs labels et leurs
  valeurs, mais les échantillons `_created` des compteurs disparaissent, et la famille d'un
  compteur prend son suffixe `_total` (`# TYPE p2pwatch_searches_total counter`).
- **Le catalogue web est toujours servi**, et `/metrics` avec lui. Retirer `"8080:8080"` des
  `ports:` de `compose.yml` le retire du réseau de l'hôte ; le réseau compose l'atteint toujours.
  S'il tombe, le crawl continue mais `/metrics` ne répond plus.
- **La notification de démarrage devient** `🟢 node online (download on)`, ou `(download off)`, au
  lieu de `🟢 instance online (mode full)` ou `(mode observer)`.
- **Dans `local.db`, la table `backfill_state` devient `reevaluation_state`**, sa colonne
  `policy_sha256` devient `policy_fingerprint`, et la table `scheduler_state` laisse place à
  `backoff_states`, une ligne par client ou canal en backoff. Les colonnes `last_seen_at` et
  `last_progress_at` de `downloads` deviennent `latest_seen_at` et `latest_progress_at`. Adaptez
  vos requêtes de la console SQL. Un backoff en cours à la mise à niveau est oublié : la recherche
  qu'il retenait repart aussitôt.
- **Dans le catalogue, la colonne `media_length_sec` devient `duration_seconds`**, désormais dans
  `observation_variants`, et la colonne `raw_meta` de `observation_variants` et de
  `source_variants` devient `raw_metadata`. Adaptez vos requêtes de la console SQL.
- **Un instant stocké en entier de microsecondes depuis l'epoch porte son unité dans son nom** :
  `observed_at` devient `observed_at_micros` dans `observations` et `source_observations` du
  catalogue, et `started_at` devient `started_at_micros` dans `backoff_states` de `local.db`.
  L'instant d'une décision, jusqu'ici un texte ISO-8601 dans `match_decisions.decided_at`, devient
  lui aussi un entier de microsecondes, `decided_at_micros`, comme les quatre instants de
  `downloads` dans `local.db` : `queued_at`, `completed_at`, `latest_seen_at` et
  `latest_progress_at` deviennent `queued_at_micros`, `completed_at_micros`,
  `latest_seen_at_micros` et `latest_progress_at_micros`. Adaptez vos requêtes de la console SQL.
- **Dans `local.db`, la table `node_runtime` devient `node_identity`**, une seule ligne : ses
  colonnes `node_id` et `created_at_micros` remplacent les clés `node_id` et `created_at`, l'instant
  devenant un entier de microsecondes. Adaptez vos requêtes de la console SQL. Un `local.db` dont
  `node_runtime` porte un `node_id` sans son `created_at` arrête la mise à niveau à sa migration
  `0015` (`NOT NULL constraint failed: node_identity.created_at_micros`) : les migrations d'avant
  restent appliquées, et le crawler ne démarre pas. Pour revenir à la 4.x, restaurez la copie de
  `local.db` qui porte le plus petit numéro ([la copie d'avant
  migration](operate.md#la-copie-davant-migration)).
- **Les paramètres d'URL de `/files` changent de nom** : `q` devient `search`, `target` devient
  `target_id` et `dir` devient `direction`. Les anciens sont ignorés : mettez à jour vos favoris.
  Un `?tier=` inconnu est ignoré lui aussi, comme un `sort` ou un `direction` inconnu : la liste
  montre tous les fichiers au lieu de n'en montrer aucun.
  Après un redémarrage depuis le tableau de bord, l'adresse se termine par `?done=restarted` au lieu
  de `?done=restart`.
- **Le crawler se lance par sa sous-commande**, `python -m p2pwatch crawl`, que l'image lance
  d'elle-même. Sans sous-commande, `python -m p2pwatch --config …` sort en erreur (code 2) :
  adaptez le `command:` que vous auriez donné au service `p2pwatch`.
- **La fusion des catalogues se lance par `python -m p2pwatch merge`**, au lieu de
  `python -m p2pwatch.merge`, qui n'existe plus. Ses options ne changent pas ; deux refus sont
  reformulés : `destination already exists` et `destination must be one of the source catalogs`.
  Une sortie `--output` qui est aussi l'une des sources est refusée (code 2) avant toute écriture,
  même avec `--force`, qui la fusionnait en elle-même : fusionnez dans ce catalogue par `--into`.
- **`validate-config` nomme le fichier en cause** : `Invalid config: <fichier>: <clé>: <message>`
  pour un contenu faux, `error: <fichier>: <raison>` sur une ligne pour un fichier absent,
  illisible ou qui n'est pas du YAML, les deux en code 1. Au démarrage, un tel fichier se lit
  `Invalid config, refusing to start: <fichier>: <raison>` au lieu de
  `unreadable YAML file: <fichier> (...)`.
- **Un texte qui n'est pas de l'UTF-8 valide est refusé**, même écrit en échappement (`"\ud800"`),
  où qu'il soit dans les trois fichiers, en nommant le fichier et sa clé :
  `error: <fichier>: search.keywords[0] is not valid UTF-8`. Une variable d'environnement que
  `crawler.yml` résout est refusée de même, en la nommant :
  `search.keywords[0]: environment variable 'X' is not valid UTF-8`. Un caractère de contrôle
  (`"\t"`, `"\x1f"`, `"\x85"`) est refusé dans une lettre de segment de `targets.yml` et dans un
  nom de règle de `matcher.yml` : `segment letter 'a\x1fb' holds a control character`. La 4.x les
  acceptait : un tel mot-clé arrêtait le crawler à sa première recherche, et un `\x1f` dans une
  lettre ou un nom de règle cassait la page des fichiers.
- **Toute erreur de `crawler.yml` commence par sa clé**, `<clé>: <message>`. Ces refus changent
  donc un peu de texte : une clé retirée ou déplacée (`port_sync: was removed, ...`), une clé
  absente (`catalog_db_path: missing` au lieu de `key 'catalog_db_path' missing`,
  `search.keywords: missing` au lieu de `search: key 'keywords' missing`), une section qui n'est
  pas un dictionnaire (`search.backoff: mapping expected, got list` au lieu de
  `section 'search.backoff': ...`), `search.backoff.factor: must be ≥ 1 (growth), got 0.5` et
  `search.backoff.cap_seconds: 1.0 < base_seconds (10.0): cap below floor`.
- **Quelques lignes de journal et noms de loggers changent** : le crawler journalise sous le nom
  du module qui écrit la ligne, qui change avec lui ; filtrez sur le message plutôt que sur le
  logger. Les échecs d'écriture de la boucle de téléchargement disent `store failure` au lieu de
  `repo failure`. Un catalogue web qui ne démarre pas le dit désormais par `webui degraded`. Les
  lignes de démarrage `crawler started` et `download enabled` journalisent sous
  `p2pwatch.application.crawler_lifecycle`, la version au démarrage sous
  `p2pwatch.composition.crawler_composition`, le dispatcher des événements sous
  `p2pwatch.application.steps.observability_dispatcher`, la réévaluation du catalogue sous
  `p2pwatch.application.steps.catalog_reevaluator` et les tâches de recherche sous
  `p2pwatch.application.steps.search_task_runner`. La recherche ne journalise plus
  `client <nom> connected` ni l'avertissement
  `client <nom> unreachable (...): reconnect backoff ...` : la session amuleapi s'ouvre d'elle-même
  au premier appel, et un amuled injoignable reste signalé par
  `client <nom> unreachable (...), client down, backoff ...`. Le port-sync,
  `mulewatch.application.port_sync_loop` en 4.x, journalise lui aussi sous le nom du module qui
  écrit la ligne : `p2pwatch_amule.application.port_sync_lifecycle`, ses commandes s6 sous
  `p2pwatch_amule.adapters.driven.s6_service_supervisor` et ses échecs à joindre gluetun sous
  `p2pwatch_amule.adapters.driven.gluetun_forwarded_port_client`.
- **La documentation** est désormais sur <https://mission-titar.github.io/p2pwatch/>.

## Retour arrière

```bash
docker compose down
mv ed2k/amule ed2k/downloads . && rm -r ed2k data
cp -a ../mulewatch.4x.bak/. .
docker compose up -d    # ou -f gluetun.compose.yml
```

Votre ancien `compose.yml` tire toujours `ghcr.io/mission-titar/mulewatch:latest`, qui reste la
4.1.0. Le catalogue revient à son état d'avant la migration.

**Sans sauvegarde de `data/`**, les copies d'avant migration en tiennent lieu ; votre
configuration, elle, vient de votre sauvegarde. Gardez alors `data/` : retirez-le du `rm -r`
ci-dessus. Puis, avant le `docker compose up -d`, cherchez les copies `pre-0006` de chaque base :

```bash
ls data/*.pre-0006.*_UTC  # la plus récente de chaque base vient en dernier
```

Restaurez seulement une base qui a une copie `pre-0006`, la plus récente : renommez-la au nom de la
base, qu'elle remplace, puis supprimez les fichiers `-wal` et `-shm` de la base, qui seraient sinon
rejoués sur la copie. Une ligne par base, que vous ne lancez que si sa copie existe :

```bash
mv data/catalog.db.pre-0006.<heure>_UTC data/catalog.db && rm -f data/catalog.db-wal data/catalog.db-shm
mv data/local.db.pre-0006.<heure>_UTC data/local.db && rm -f data/local.db-wal data/local.db-shm
```

Une base sans copie `pre-0006` n'a jamais été migrée : laissez-la telle quelle. C'est le cas de
`local.db` quand la migration du catalogue a échoué, car le crawler ouvre le catalogue d'abord.
