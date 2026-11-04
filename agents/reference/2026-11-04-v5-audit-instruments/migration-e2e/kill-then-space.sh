#!/bin/sh
# kill-then-space.sh SIZE ENVFILE: a tmpfs volume kept mounted by a holder; SIGKILL the crawler as
# migration 7 starts, then start it again on the same data and print how it ends.
E=/home/geoffrey/Repositories/emule-indexer/.e2e
K=$E/node-kill
V=v5audit-e2e-fsvol
docker volume create --driver local --opt type=tmpfs --opt device=tmpfs --opt "o=size=$1,mode=1777" $V >/dev/null
docker run -d --name v5audit-e2e-holder --network none --user 1000:1000 -v $V:/data -v "$E/small-4x:/seed:ro" \
  --entrypoint sh p2pwatch:v5audit -c 'cp /seed/* /data/ && sleep 100000' >/dev/null
sleep 3
crawl() {
  docker run -d --name "$1" --network none --user 1000:1000 --env-file "$2" -v $V:/data \
    -v "$K/crawler.yml:/app/config/crawler.yml:ro" -v "$K/targets.yml:/app/config/targets.yml:ro" \
    -v "$K/matcher.yml:/app/config/matcher.yml:ro" -v "$K/ed2k/downloads:/downloads:ro" \
    p2pwatch:v5audit >/dev/null
}
crawl v5audit-e2e-run-a "$2"
until docker logs v5audit-e2e-run-a 2>&1 | grep -q 'migration 7: applying'; do sleep 0.1; done
docker kill v5audit-e2e-run-a >/dev/null
echo "== after kill"; docker exec v5audit-e2e-holder sh -c 'ls -la /data; df -B1 /data | tail -1'
crawl v5audit-e2e-run-b "$2"
sleep 8
echo "== second start: $(docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}}' v5audit-e2e-run-b)"
docker logs v5audit-e2e-run-b 2>&1 | grep -E 'pre-migration|migration [0-9]+:|MigrationError|crawler started'
docker exec v5audit-e2e-holder ls -la /data
docker rm -f v5audit-e2e-run-a v5audit-e2e-run-b v5audit-e2e-holder >/dev/null
docker volume rm $V >/dev/null
