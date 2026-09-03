-- Data cleanup, 2026-08-20. Approved by Gabe.
--
-- 1. Removes ONE duplicate person node. "Иван Петров Иванов" exists twice:
--    once with his real papagal key (0b73f268…) and once with a synthetic tr- key
--    minted while papagal was Cloudflare-blocked. The tr- node's 2 edges are exact
--    duplicates of edges the real node already carries, so nothing unique is lost.
--    Both DELETEs are guarded: an edge is dropped only when the real node already
--    has the same (dst, relation), and the node only when it has no edges left.
--
-- 2. Nulls share_pct on papagal-sourced edges. Papagal renders a person's entire
--    ownership history as sibling rows and marks several of them "current", so the
--    scraper stored the OLDEST value — Георги Георгиев in Смарт Хаус was recorded at
--    50% when the register says 26% (1300 of 5000 лв). Verified and stale values
--    are indistinguishable today, so unverified ones are cleared and will be
--    re-derived from the Търговски регистър. Edges already sourced from the
--    register keep their authoritative percentages.
--
-- Never touches "user" or "oauth_account" — the row count is printed before and
-- after so it can be checked. Runs in ONE transaction; any error rolls it all back.
--
-- Run on the VPS:
--   cd ~/projects/bg-realestate-intel
--   set -a; source /home/deploy/secrets/pocketbroker.env; set +a
--   psql "${DATABASE_URL/postgresql+psycopg:/postgresql:}" \
--        -v ON_ERROR_STOP=1 -f deploy/cleanup_20260820_dedupe_and_shares.sql

\set ON_ERROR_STOP on
BEGIN;

\echo '--- BEFORE ---'
SELECT 'users (must not change)' AS what, count(*)::text AS n FROM "user"
UNION ALL SELECT 'tr- person nodes', count(*)::text FROM entity WHERE person_key LIKE 'tr-%'
UNION ALL SELECT 'edges w/ papagal share_pct', count(*)::text FROM entity_edge
          WHERE share_pct IS NOT NULL AND source LIKE '%papagal%';

\echo '--- the duplicate and its real counterpart ---'
SELECT e.id, left(e.person_key, 24) AS key, e.name,
       (SELECT count(*) FROM entity_edge x
         WHERE x.src_entity_id = e.id OR x.dst_entity_id = e.id) AS edges
FROM entity e
WHERE e.person_key IN (
  'tr-03676c63bdb75544456683aab5edc41506b461e127b56aba5ed8cfeaedd96f55-1',
  '0b73f268914b76b573d8aaead2b8439a8002d91bdeaacafdc8e74d3312c9d33b-1');

-- 1a. Drop the duplicate's edges, only where the real node has an identical one.
DELETE FROM entity_edge ee
USING entity dup, entity real_e
WHERE dup.person_key = 'tr-03676c63bdb75544456683aab5edc41506b461e127b56aba5ed8cfeaedd96f55-1'
  AND real_e.person_key = '0b73f268914b76b573d8aaead2b8439a8002d91bdeaacafdc8e74d3312c9d33b-1'
  AND ee.src_entity_id = dup.id
  AND EXISTS (SELECT 1 FROM entity_edge k
              WHERE k.src_entity_id = real_e.id
                AND k.dst_entity_id = ee.dst_entity_id
                AND k.relation = ee.relation);

\echo '--- edges left on the duplicate (must be 0 before it is removed) ---'
SELECT count(*) AS remaining FROM entity_edge ee
JOIN entity dup ON dup.person_key = 'tr-03676c63bdb75544456683aab5edc41506b461e127b56aba5ed8cfeaedd96f55-1'
WHERE ee.src_entity_id = dup.id OR ee.dst_entity_id = dup.id;

-- 1b. Remove the now-orphaned duplicate node.
DELETE FROM entity
WHERE person_key = 'tr-03676c63bdb75544456683aab5edc41506b461e127b56aba5ed8cfeaedd96f55-1'
  AND NOT EXISTS (SELECT 1 FROM entity_edge x
                  WHERE x.src_entity_id = entity.id OR x.dst_entity_id = entity.id);

-- 2. Clear the unreliable percentages (papagal person-page origin only).
UPDATE entity_edge SET share_pct = NULL
WHERE share_pct IS NOT NULL
  AND source LIKE '%papagal%'
  AND source NOT LIKE '%registryagency%';

\echo '--- AFTER ---'
SELECT 'users (must not change)' AS what, count(*)::text AS n FROM "user"
UNION ALL SELECT 'tr- person nodes', count(*)::text FROM entity WHERE person_key LIKE 'tr-%'
UNION ALL SELECT 'edges w/ unverified share_pct', count(*)::text FROM entity_edge
          WHERE share_pct IS NOT NULL AND source LIKE '%papagal%' AND source NOT LIKE '%registryagency%'
UNION ALL SELECT 'edges w/ verified share_pct', count(*)::text FROM entity_edge
          WHERE share_pct IS NOT NULL AND source LIKE '%registryagency%';

COMMIT;
