# Developer Research Playbook — research protocol (phases 0–8)

**Use for:** any Bulgarian real estate developer not yet in the DB.
**Reference cases:** redacted — worked examples name private individuals and are kept out of this public mirror.

**SPV** = *Special Purpose Vehicle* — a company holding one single project. BG developers register
one ЕООД per building, so permits, mortgages, pre-sale contracts and **lawsuits attach to the SPV,
not the parent brand**. That is why we trace the ownership graph before anything else.

**Signal order (highest-value first):** OFFICIAL court records (Phase 6) → then COMMUNITY/WEB
news & forum (Phase 7). Court records come first and on their own carry the most weight.

---

## Phase 0 — Pre-flight

Record what you already know before touching any tool:

| Item | Notes |
|------|-------|
| Raw brand name(s) | e.g. "Грийн Лайф", "Green Life City" |
| ЕИК (if known) | — |
| Known projects | Нова Дружба, CAVA HOME, … |
| Complaint context | Forum threads, issue type |

Then check the DB — is anything already loaded?

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Entity
db = SessionLocal()
rows = db.scalars(select(Entity).where(Entity.name.ilike('%<term>%'))).all()
for e in rows: print(e.eik, e.name, e.is_builder, e.status)
db.close()
"
```

If results exist with `is_builder=True` and signals → already done. If only orphan edges → continue from Phase 5.

---

> ## ⛔️ Papagal is blocked (2026-08-20) — use the official register
>
> papagal.bg sits behind a Cloudflare managed challenge (`cf-mitigated: challenge`);
> every path including the homepage returns 403 and headless Chromium cannot clear it.
> **`crawlers/scraper_kit/sites/papagal.py` is non-functional.**
>
> Replacement: **`crawlers/scraper_kit/sites/registryagency.py`** — the official
> Търговски регистър, via the JSON API its own portal calls. No CAPTCHA, no session,
> plain HTTP. Emits the same record shape, so `etl.load_ownership` is unchanged.
>
> ```bash
> python3 -m crawlers.scraper_kit.sites.registryagency --eik 203879071
> python3 -m crawlers.scraper_kit.sites.registryagency --eiks-file eiks.txt \
>     --person-key-map keymap.tsv     # reuse existing graph person_keys
> ```
>
> It also returns two things papagal never did: **обхват на дейност** (tells a builder
> from a shop) and **запор върху дружествен дял** — share attachments with creditor and
> enforcement case number. The запор is a serious distress signal and it is **invisible
> to legalacts.justice.bg**, because enforcement runs before a частен съдебен изпълнител,
> not a court. Phase 6 alone will therefore miss it — always read the register too.
>
> Caveats: rate-limits to 429 above ~1 req/3s; and it exposes no person id, so person
> keys are derived from the name and namespaced `tr-`. Same-name people collide.
> See the module docstring before merging any person node.

## Phase 1 — Identify the canonical ЕИК

The brand name in a forum post or press article almost never matches the registered company name exactly.

```python
import httpx, time
from bs4 import BeautifulSoup
headers = {'User-Agent': 'Mozilla/5.0 (compatible; bg-realestate-intel/1.0)'}
r = httpx.post('https://papagal.bg/s', data={'query': '<brand name>'}, headers=headers,
               follow_redirects=True, timeout=15)
soup = BeautifulSoup(r.text, 'html.parser')
for a in soup.find_all('a', href=True):
    if '/eik/' in a['href']:
        print(a['href'], '|', a.get_text(strip=True))
```

- Run for each name variant (Bulgarian + English transliteration)
- If multiple hits: note ALL ЕИКs — one may be the brand (ЕАД), one the licensed entity (ЕООД)
- **Output:** canonical ЕИК + full legal name

---

## Phase 2 — Core entity: pull company page + trace the chain UP

```bash
python3 -m crawlers.scraper_kit.sites.papagal --eik <ЕИК>
# output → data/raw/ownership/bg/papagal_<date>_<run-id>.jsonl
# (run-id is a random 8-hex token per run — every invocation gets its own file,
#  so concurrent/same-day sessions can't clobber each other; glob for the latest)
```

Read the record and check:

```python
import glob, json
latest = max(glob.glob('data/raw/ownership/bg/papagal_*.jsonl'), key=lambda p: __import__('os').path.getmtime(p))
with open(latest) as f:
    for line in f:
        r = json.loads(line)
        if r.get('eik') == '<ЕИК>':
            print(json.dumps(r, ensure_ascii=False, indent=2))
```

**Key checks:**
| Field | What to look for |
|-------|-----------------|
| `status` | "Активен" = live; "несъстоятелност"/"ликвидация"/"заличен" = distressed |
| `capital_eur` | Low (< €5 000) = likely SPV shell |
| `related[].kind == 'person' and role == 'Едноличен собственик'` | UBO — is it a person or another company? |

**If the owner is another company** → pull it too. Repeat until a natural person appears as UBO. This traces the chain UP through holding layers.

---

## Phase 3 — Breadth: siblings + brand/parent

From Phase 2 you now have company-owners and brand names. Search for siblings:

```python
# Search for the brand root to find all related EIKs
r = httpx.post('https://papagal.bg/s', data={'query': '<brand>'}, ...)
# Collect all /eik/ links
```

Also search for the known project names if they suggest separate SPVs.

Batch-pull all new ЕИКs:

```bash
printf '175179187\n200151449\n102824466\n' > /tmp/<slug>_eiks.txt
python3 -m crawlers.scraper_kit.sites.papagal --eiks-file /tmp/<slug>_eiks.txt
```

---

## Phase 4 — Depth-2: person expansion (SPV constellation)

Extract person_keys from all scraped records:

```python
import json, glob

persons = {}
for path in glob.glob('data/raw/ownership/bg/papagal_*.jsonl'):
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            for rel in r.get('related', []):
                pk = rel.get('person_key', '')
                name = rel.get('name', '')
                # Real person hashes are long hex strings
                if rel['kind'] == 'person' and '-' in pk and len(pk.split('-')[0]) > 20:
                    persons[pk] = name

for pk, name in persons.items():
    print(f'{pk}\t{name}')
```

Write to TSV and run depth-2:

```bash
python3 -m crawlers.scraper_kit.sites.papagal --persons-file /tmp/<slug>_persons.tsv
# output → data/raw/ownership/bg/papagal_persons_<date>_<run-id>.jsonl
```

**What to look for in results:**
- Companies with very high ЕИК numbers (recently incorporated) → new SPVs
- Capital ≤ €51 → pure shell, likely a project vehicle
- Company names matching known project names or addresses

---

## Phase 5 — Load into DB

```bash
cd backend && .venv/bin/python -m etl.run_phase35
# reports: companies created, persons created, edges upserted
```

Then mark the primary developer(s) as builders:

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Entity
db = SessionLocal()
for eik in ['<EIK1>', '<EIK2>']:   # brand + licensed entity
    e = db.scalar(select(Entity).where(Entity.eik == eik))
    if e:
        e.is_builder = True
        print('set is_builder on', e.name)
db.commit(); db.close()
"
```

---

## Phase 6 — OFFICIAL court records (legalacts.justice.bg) — FIRST signal source, human-in-the-loop

> ⚖️ **EXISTENCE ≠ GUILT.** The mere existence of court cases does **not** mean the company or
> builder is fraudulent — companies litigate routinely. We record the **existence** of public
> acts as evidence to review, never as a verdict. (The UI already shows this disclaimer.)

> This is the **agreed human-in-the-loop flow** (design spec
> `2026-06-02-official-records-check-design.md`, Component A): **the assistant drives the search
> and self-solves the CAPTCHA, up to 3 attempts per search.** If all 3 attempts on a given search
> fail, skip that search and move to the next one — don't burn turns retrying the same image.
> Queue the skipped (hard) searches and solve them together with the operator at the end of the
> session. Never use an automated solver service. Court records are the highest-value trust
> signal → they come **before** news/forum.

### 6a. ASK first — scope of the search (gate 3.3)

Before searching, **STOP and ask the operator** (AskUserQuestion): run the court search for
**only the main builder/SPV**, or for **every entity connected in the ownership web** (all graph
nodes)? Wait for the answer — do not auto-expand to the whole graph.

### 6b. Search — list only, do NOT open the PDFs

The only free-text field is **Ключови думи** (Lucene full-text over act *bodies*). There is **no
party/ЕИК field**, and the listing is anonymised. Run **TWO searches and UNION them** (neither is
a superset — verified 2026-06-07 on Грийнлайф Плейс):

- **(a) by ЕИК digits**, e.g. `205419303`, **Съд = Всички** (do NOT filter court). Primary,
  highest-precision pass: the ЕИК is in the party block → spans **all instances** (СГС → АС →
  **ВКС**) and the **commercial division** (Търговско).
- **(b) by SPV name**, e.g. `Грийнлайф Плейс`. Catches **procedural определения** that cite the
  party by name but omit the ЕИК digits (which the ЕИК pass misses).
- Example delta: (a)=10 acts (incl. 2 ВКС cassation + 3 СГС), (b)=7 → **union = 12**.

CAPTCHA (`/captcha.ashx`): **screenshot `img[alt="CAPTCHA"]`, read it yourself, submit a guess.**
Up to 3 attempts per search (each wrong guess regenerates the image — re-screenshot before
retrying). After 3 failures, abandon that search, note it as a queued hard case, and continue
with the next entity/search. At the end of the round, go through the queued hard cases together
with the operator (screenshot + ask).

Field selectors (stable IDs — avoid re-snapshotting the huge court dropdown): keyword `#KeyWord`,
court `#CourtId`, CAPTCHA input `#Captcha`, CAPTCHA image `img[alt="CAPTCHA"]`, submit
`button.button-search`.

### 6c. Save the LIST to DB (metadata only — no PDF reading)

Capture each result row's **metadata only**: court · act type + number · date · in-force date ·
case number · case type · `/Search/Details?actId=<token>` URL. **Do not open the ruling PDFs.**
The scraper writes its own `legalacts_<date>_<run-id>.jsonl` automatically (every
run gets a unique `run-id`, so same-day sessions never clobber each other);
`run_signals` globs both `registry_*.jsonl` and `legalacts_*.jsonl`, so renaming
to `registry_<slug>_<date>.jsonl` is no longer required for collision-safety —
do it only if you want a more readable filename. Then
`cd backend && .venv/bin/python -m etl.run_signals`.

```jsonl
{"matched_eik": "<SPV ЕИК>", "matched_name": "<SPV name>", "url": "https://legalacts.justice.bg/Search/Details?actId=<token>", "title": "<court>, <act type> № <n> от <date> по <case>", "snippet": "<court / case type / in-force — metadata only>", "source_site": "legalacts.justice.bg", "observed_date": "<YYYY-MM-DD>"}
```

### 6d. ASK before going one level down (gate 3.1)

If cases are found, **STOP and ask the operator**: should I open and read the rulings? **Only
WITH permission** open the PDF (Изтегли → save the file → **Read it directly with the native Read
tool** via the `pages` parameter — no screenshotting needed; Read ingests both the PDF text and the
rendered pages) to confirm the company is a **party** and read the outcome, then enrich the
snippet. Without permission, the existence-only list stands.

> **Why ЕИК-match is safe:** an ЕИК-digit body hit is near-certain to be the party (digits live in
> the party identification block). **Name** searches can be ~2/3 false positives (namesakes) — so
> if you went one level down, verify name-only hits before asserting party status.

---

## Phase 7 — Community + web signals (news, forum)

> Run **after** the official court check. News/TV, buyer-run trackers (`indexation.bg`) and
> watchdog FB pages ("Правосъдие за всеки") yield only **community/web**-tier signals — supporting
> colour, never an official-tier act. The scandal usually **breaks in the news, not the forum.**

### 7a. Pre-check the name matcher (before the ETL)

```python
import sys; sys.path.insert(0, '.')
from crawlers.signals.match import distinctive_terms, _STOPWORDS
name = "ГРИЙНЛАЙФ-ПРОПЪРТИ"   # replace
print('Terms:', distinctive_terms(name, 'company'))
# empty / only 1 very common term → will be pruned → manual insert needed
```

| Situation | Symptom | Fix |
|-----------|---------|-----|
| Name splits to only stopwords | `terms = []` | Manual insert with `match_confidence='eik'` |
| Single token shared by 20+ companies | Token pruned by `index_targets` | Same |
| Person name has no patronymic | "Николай Николов" ≠ "<име на физическо лице>" | Manual insert |
| Forum two-word brand vs DB one-word | "Грийн Лайф" ≠ "ГРИЙНЛАЙФ" | Manual insert |

### 7b. News / web layer

```
"<brand>" (измама OR жалба OR дело OR съд OR прокуратура OR фалит OR недостроен)
"<UBO name>" <brand>        # owners with a public profile (ex-politician etc.)
"<project name>" скандал
```

Write hits to `data/raw/signals/sofia/web_<date>_<run-id>.jsonl` (via `write_hits()` —
the `run-id` is automatic) with an **explicit** `matched_name` =
the DB entity's full legal name. `load_web()` keys on that name and **bypasses the fuzzy matcher**
— so stopword pruning / two-word-vs-one-word does NOT apply here. One JSONL line per article:

```jsonl
{"matched_name": "ГРИЙНЛАЙФ-ПРОПЪРТИ ЕООД", "subject_kind": "company", "title": "...", "url": "...", "snippet": "...", "observed_date": "2025-09-24", "source_site": "capital.bg", "scraped_at": "<ISO>"}
```

🚩 **Exit-vehicle pattern:** a developer dodging buyer claims **transfers pre-sold assets to a
brand-new company** incorporated days earlier (Грийнлайф → **РЕЗИДИА ГРУП АД**, ЕИК 208423470,
took 130+ flats just after incorporation). When the news names a fresh AD absorbing inventory,
**scrape that ЕИК in Papagal** (Phase 2-style) — it's the heart of the scheme and often a node
not yet in your graph.

### 7c. Forum / community manual insert (when the ETL misses known posts)

```python
from datetime import date, datetime
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Entity, EntitySignal
db = SessionLocal()
e = db.scalar(select(Entity).where(Entity.eik == '<ЕИК>'))
posts = [
    {"url": "https://bg-mam.ma/p/<thread>/<post_id>", "title": "BG-Mamma — тема <thread>",
     "snippet": "<key text>", "observed_date": date(2022, 3, 15),
     "scraped_at": datetime.fromisoformat("<ISO>")},
]
for post in posts:
    if db.scalar(select(EntitySignal).where(EntitySignal.url == post['url'],
                                            EntitySignal.matched_name == e.name)):
        continue
    db.add(EntitySignal(entity_id=e.id, subject_kind='company', matched_name=e.name,
        matched_eik=e.eik, source_type='forum', tier='community', match_confidence='eik',
        title=post['title'], snippet=post['snippet'], url=post['url'], source_site='bgmamma',
        observed_date=post['observed_date'], scraped_at=post['scraped_at']))
db.commit(); db.close()
```

### 7d. Run the ETL

```bash
cd backend && .venv/bin/python -m etl.run_signals
# reports: targets, forum_signals, web_signals, registry_signals, skipped_existing
```

---

## Phase 8 — Findings document

Write `docs/<SLUG>_RESEARCH_FINDINGS.md` with these sections:

```
## 0. TL;DR         (2–3 sentence summary)
## 1. Key identifiers  (ЕИК table)
## 2. Ownership chain  (ASCII diagram: UBO → holding → brand → SPVs)
## 3. SPV catalogue    (table: ЕИК, name, probable project)
## 4. Complaints       (signal table by tier: official / community / web)
## 5. КСБ status       (licensed? if yes: which entity; if no: note it)
## 6. DB status        (entity_id, is_builder flag, signal count, edge count)
## 7. Outstanding gaps (what's still unknown or not loaded)
## 8. Quick recipes    (copy-paste commands for common follow-up tasks)
## 9. Pointers         (links to raw data files, related docs, memories)
```

---

## Common pitfalls (learned from Артекс + Грийнлайф)

| Pitfall | Rule |
|---------|------|
| Brand ≠ licensed entity | Always pull the company that appears in the KSB register separately from the brand |
| Owner is a company | Trace UP until a human UBO; every extra layer = deliberate opacity |
| Same family name ≠ same person | Patronymics disambiguate: Пламен **Пламенов** ≠ Пламен **Младенов** Иванов |
| Court cases live in SPVs | Search legalacts for the **project SPV ЕИК**, not the brand |
| **Court records come FIRST** | Official court check (Phase 6) before news/forum (Phase 7); news is a supplement |
| **Existence ≠ guilt** | Recording that court acts exist is evidence to review, not a verdict |
| **Don't auto-expand or auto-read** | ASK before reading rulings (gate 3.1) and before searching every connected entity (gate 3.3) |
| **CAPTCHA = 3 attempts, then queue** | Self-solve from the screenshot, up to 3 tries per search; after 3 fails, skip and queue it; solve queued hard cases with the operator at the end |
| **ЕИК search ≠ name search** | On legalacts, union both: ЕИК (all courts, all instances) + name (procedural определения) |
| **Scandal breaks in the news** | Run the Phase 7b web search; `load_web()` bypasses the fuzzy matcher when `matched_name` is set |
| **Exit-vehicle SPV** | A fresh AD absorbing pre-sold inventory (Резидиа груп, ЕИК 208423470) is the core of the scheme — scrape its ЕИК |
| **АД walls off the UBO** | When the exit vehicle is an **АД** (not ЕООД/ООД), shareholders are **not public** in ТР — Papagal shows only the board, often **nominees** (Резидиа: Драгомирова/Тренев/НОУПРО, none linked to the brand). The brand↔vehicle link then lives only in the news, not the register. Don't expect Papagal to reveal who really owns an АД. |
| Name matcher silently fails | Always do the Phase 7a pre-check; insert manually when needed |
| "ГРИЙН ЛАЙФ ПРОПЪРТИ-2222" trap | Name overlap ≠ ownership link; verify via Papagal before including in the group |
