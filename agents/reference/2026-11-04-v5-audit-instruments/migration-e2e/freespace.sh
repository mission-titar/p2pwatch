#!/bin/sh
# freespace.sh SIZE NAME: the crawler on a tmpfs /data of SIZE seeded with .e2e/small-4x, no network.
E=/home/geoffrey/Repositories/emule-indexer/.e2e
K=$E/node-kill
docker run -d --name "v5audit-e2e-$2" --network none --user 1000:1000 \
  --env-file "$3" \
  --mount "type=tmpfs,destination=/data,tmpfs-size=$1,tmpfs-mode=1777" \
  -v "$E/small-4x:/seed:ro" \
  -v "$K/crawler.yml:/app/config/crawler.yml:ro" -v "$K/targets.yml:/app/config/targets.yml:ro" \
  -v "$K/matcher.yml:/app/config/matcher.yml:ro" -v "$K/ed2k/downloads:/downloads:ro" \
  --entrypoint sh p2pwatch:v5audit -c \
  'cp /seed/* /data/ && df -B1 /data && exec python -m p2pwatch crawl --config /app/config/crawler.yml --targets /app/config/targets.yml --matcher /app/config/matcher.yml'
