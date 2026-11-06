---
paths:
  - "packages/amule/**"
  - ".github/**"
---

# The aMule container

- **The core mounts the output directory read-only**, for the disk floor's `statvfs` only. One deliberate exception, in the aMule container: its boot step (`python -m p2pwatch_amule boot`) creates the mount points `/downloads/incoming` and `/downloads/temp` and chowns them, not recursively, to `PUID:PGID`, so that amuled, running as `amule`, can write there. It runs once as root before s6 starts anything, the crawler never imports it, and it never lists, opens or changes what the mounts contain. It lives in `packages/amule/`, under the same gate (mypy, coverage, the VEX source claims check).
- **A service that exits unasked takes the container down**: each `docker/services.d/<service>/finish` runs `s6-svscanctl -t` when `s6-svstat -o wantedup .` reads `true`, and Docker's `restart: unless-stopped` restarts the container. The guard is what keeps `docker stop` and `s6-svc -d` (the port-sync's amuled restart) from doing the same; a new service gets the same `finish`. amuleapi is amuled's child, not a service: its loss shows only as `unhealthy`.
- **aMule's version lives only in `packages/amule/Dockerfile`** (`ARG AMULE_VERSION` + `ARG AMULE_COMMIT`, bumped weekly by `.github/workflows/amule-bump.yml`): never write it anywhere else.
