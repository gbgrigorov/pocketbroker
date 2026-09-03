# Official alternatives to papagal.bg — field-by-field

**Date:** 2026-08-20
**Why:** papagal.bg went behind a Cloudflare managed challenge for automated clients
(`cf-mitigated: challenge`; it still loads in a normal browser). It was the only source
feeding the ownership graph, so the question is whether **official** registers can replace
it without losing capability.

**Answer: yes, and on the things that matter for this product the official sources are
better.** Everything below was verified against a real Papagal page for СМАРТ ХАУС КЪМПАНИ
ООД (ЕИК 203879071) captured on 2026-08-20, compared field by field.

---

## The verdict

| Papagal field | Official source | Verified? | Notes |
|---|---|---|---|
| Статус | ТР `deedStatus` | ⚠️ partial | `1` = active. Other codes not yet observed — do not guess them |
| ЕИК/ПИК | ТР field 1 | ✅ | |
| Наименование | ТР field 2 | ✅ | ТР omits the legal-form suffix; Papagal appends it |
| Транслитерация | ТР field 4 | ✅ | |
| Правна форма | ТР field 3 | ✅ | |
| Дата на регистрация | ТР field entry date | ✅ | 2016-01-19, matches |
| Седалище адрес | ТР field 5 | ✅ | ТР is more verbose but complete |
| Предмет на дейност | ТР field 6 | ✅ | **Papagal truncates it in the free view; ТР gives it in full** |
| Представляващи | ТР field 7 | ✅ | Георги Георгиев, Иван Иванов — matches |
| Собственост + % дял | ТР field 19 | ✅ | ТР gives the **BGN amount** (2500/1300/1200 of 5000); the % is arithmetic |
| Едноличен собственик | ТР field 23 | ✅ | Papagal folds this into "Собственост" |
| Капитал размер | ТР field 31 | ✅ | 2 556.46 € — matches |
| "свързан с N фирми" | ТР `SubjectInFields` | ✅ | Returns the actual company list, not just a count |
| Дъщерни дружества | ТР `SubjectInFields` | ⚠️ partial | Works for persons; company-as-subject not yet tested |
| **Оборот / финансови показатели** | **ГФО PDFs in the ТР** | ✅ | See below — this is the important one |
| **Регистрация по ЗДДС** | **VIES (EU) / НАП** | ✅ | Not in the ТР at all |
| **Запор върху дружествен дял** | **ТР only** | ✅ | **Papagal does not show this. See below.** |

---

## 1. Financials — Papagal is parsing the ТР's own PDFs

Papagal's page carries its own disclaimer: *"Финансовите данни са извлечени автоматично…
възможни грешки и неточности."* They are parsed from the annual financial reports published
in the Търговски регистър, which we can fetch ourselves.

The ТР's `Deeds` payload lists every filed ГФО by year with a download token
(`CR_F_1001_L` → `DocumentAccess/<token>`), and the document itself comes from:

```
GET https://portal.registryagency.bg/CR/api/Documents/{token}     -> application/pdf
```

Plain curl. Verified: the 2017 ГФО for 203879071 downloads as a 648 KB, 6-page PDF.

**Cross-check against Papagal's own numbers (2017, хил. лв):**

| Line | Papagal | Official ГФО | |
|---|---|---|---|
| Приход | 6 | 6 | ✅ |
| Оперативни разходи | 14 | 14 | ✅ |
| Счетоводна печалба | −27 | загуба 27 | ✅ |

Exact match — which confirms Papagal adds no data here, only extraction.

**The official PDF carries more than Papagal's free tier shows:** full balance sheet (сума
на активите 1 194 хил. лв; задължения към финансови предприятия 1 003; получени аванси
1 003; парични средства 230; земи и сгради 850) and a complete cash-flow statement.

And critically: **Papagal locks 2021+ behind a PRO subscription. The ТР gives every year
free.** For a company whose revenue went 1.86M лв (2022–23) → 41k лв (2020), the recent
years are exactly the ones that matter.

Cost of switching: the ГФО is a **scanned PDF**, so the numbers need OCR/extraction rather
than a regex. That is the one place Papagal genuinely saved us work.

## 2. Ownership graph — fully replaceable, via two JSON endpoints

```
GET /CR/api/Deeds/{eik}?entryDate=<iso>&loadFieldsFromAllLegalForms=false
GET /CR/api/Deeds/Subjects?name=<name>&selectedSearchFilter=0     -> [{isPhysical, ident, name}]
GET /CR/api/Deeds/SubjectInFields?uid=<ident>&name=<name>&type=1  -> [{companyFullName, uic, fieldName}]
```

No CAPTCHA, no session, no JS — plain HTTP returning JSON. `SubjectInFields` is the
depth-2 person expansion that actually builds a constellation, and the `fieldName` tells you
the relation (`CR_F_7_L` управител, `CR_F_19_L` съдружник, `CR_F_23_L` едноличен собственик).

Verified: ИВАН ПЕТРОВ ИВАНОВ → АБ Кълекшън, КАБА ИНТЕРНЕШЪНЪЛ, АРТСТРОЙ, with roles.

**Two real losses versus Papagal:**

1. **No stable person id.** The register keys people on ЕГН and will not disclose it. The
   `ident` token is re-encrypted per request, so it cannot be stored as a key. Papagal's
   opaque per-person hash was genuinely better, and losing it is the single biggest
   regression. Our fallback is a name-derived `tr-` key — **same-name people collide.**
2. **No "свързан с N фирми" count** without making the second call per person.

## 3. What the official register has that Papagal does not

**Запор върху дружествен дял** — attachment of a partner's share, with creditor,
enforcement case number and the amount of capital affected (section
`CR_APP_ARREST_SHARE_L`).

This is not a footnote. For СМАРТ ХАУС КЪМПАНИ the register shows **3 800 of 5 000 лв — 76%
of capital — under attachment** since 2024-02-09 (изп. дело № 20247900400356). The Papagal
page for the same company shows **Статус: Активен** and nothing else; the attachment does
not appear anywhere on it.

It is also invisible to legalacts.justice.bg, because enforcement runs before a частен
съдебен изпълнител rather than a court. **A company can therefore look clean in both
Papagal and the court portal while most of its capital is attached.** For a product whose
purpose is flagging developer risk, this alone justifies the switch.

## 4. ЗДДС — VIES

Not held by the ТР. The official EU validation service:

```
GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/BG/vat/{eik}
-> {"isValid": true, "name": "...", "address": "..."}
```

Verified for 203879071. Gives validity, name and address, but **not** Papagal's registration
date or legal basis (чл. 100 ал. 1). НАП's own public check would be needed for those.

## 5. Sources checked and rejected

| Source | Verdict |
|---|---|
| `data.egov.bg` | **403** to automated clients |
| OpenCorporates API | Requires a paid token; not signing up |
| БУЛСТАТ | Non-traders only — wrong population |
| Papagal via headed browser | Loads normally for a human. Viable as a **manual** lookup, not as a pipeline |

---

## Recommended stack

| Need | Source |
|---|---|
| Identity, ownership, managers, capital, activity, **запори** | **ТР `Deeds` API** — `crawlers/scraper_kit/sites/registryagency.py` |
| Person → companies (network building) | **ТР `Subjects` + `SubjectInFields`** |
| Financial history | **ГФО PDFs via ТР `Documents` API** (needs OCR) |
| ЗДДС status | **VIES** |
| Court acts | legalacts.justice.bg (unchanged) |
| Financial figures, quickly, by hand | papagal.bg in a browser — convenience only, never the pipeline |

## Open work

- [ ] Map the remaining `deedStatus` codes (need a known struck-off / insolvent company)
- [ ] Resolve the `tr-` vs papagal `person_key` collision — a reconciliation pass, reviewed, never an automatic name merge
- [ ] OCR pipeline for ГФО PDFs to recover the financial series
- [ ] Test `SubjectInFields` with a company as subject (дъщерни дружества)
- [ ] Back-fill `activity` and `запор` for the ~750 papagal-sourced companies already in the graph — none has ever been checked for an attachment
