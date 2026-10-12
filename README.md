# p2pwatch

p2pwatch surveille en continu le réseau eMule (eD2k + Kad) pour retrouver des médias perdus. Sa
première mission : la version française de *Keroro mission Titar* (Teletoon, 2008), aujourd'hui
quasiment introuvable. Ces épisodes n'ont pas tout à fait disparu : ils refont surface par
intermittence, le temps qu'un détenteur reste connecté, puis s'évanouissent. Une recherche manuelle
tombe presque toujours au mauvais moment ; une veille permanente, non. Un nœud cherche sans relâche,
catalogue ce qu'il croise, et alerte dès qu'un épisode manquant apparaît. Le catalogue enregistre
des fichiers et, là où un protocole en publie un, **l'identifiant pseudonyme de la source qui les
partageait**, pour qu'un chercheur puisse reconnaître un partageur récurrent et contacter un
archiviste possible. Il ne stocke jamais l'adresse réseau d'un pair (IP, port, pays), et ne relie
jamais des identifiants d'un réseau à l'autre.

**[Documentation complète](https://mission-titar.github.io/p2pwatch/)** : installer un nœud, le
faire tourner, le dépanner, et ce qu'il faut savoir côté légalité et vie privée.

## Développement

```bash
./scripts/setup-dev.sh   # environnement (uv sync --dev) et hook pre-push
uv run poe check         # le gate complet : lint, types, SQL, tests
```

Les conventions et invariants du projet sont dans [`AGENTS.md`](AGENTS.md) ; les specs, plans et
handoffs dans [`agents/`](agents/).
