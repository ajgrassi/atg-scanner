# ATG Deal Scanner

**Owner:** Andrew Grassi / ATG Investments LLC
**Runtime:** Claude Code Routine (scheduled daily, 6:30am Central)
**Purpose:** Read broker alert emails from a dedicated Gmail inbox, parse listings (text body + PDF attachments), score them against ATG investment thesis, create a draft digest email that is auto-sent by a companion Google Apps Script.

---

## Architecture: draft-then-autosend

The built-in Claude Gmail connector can READ emails and CREATE drafts, but it CANNOT SEND emails. To bridge this:

1. **6:30am CT — Claude Routine fires.** Reads broker emails, scores listings, creates a Gmail draft with subject prefixed `[ATG-DIGEST-AUTOSEND]`.
2. **6:35am CT — Google Apps Script fires.** Searches drafts for the prefix, sends them, strips the prefix from the subject, deletes the original draft.

The Apps Script (`apps_script/atg_digest_autosender.gs`) is installed in the user's Google account and runs on a daily time-based trigger. It never touches drafts that don't have the magic prefix.

---

## Gmail account configuration

**Account used:** `agrassi@ybpsrv.com` (already connected to the user's Claude account as the Gmail connector)

**No dedicated scanner inbox needed.** All broker email subscriptions go to `agrassi@ybpsrv.com` directly. The scanner uses Gmail search filters to identify broker emails:

```
from:(noreply@crexi.com OR alerts@loopnet.com OR sandsig.com OR ...)
  newer_than:1d
```

The user maintains Gmail filters/labels to keep broker emails organized in the inbox (recommended: a "Deal Flow" label that auto-applies to all broker domains).

---

## What this routine does on each run

1. Connect to Gmail via the built-in Claude Gmail connector
2. Query for emails from broker domains (see `SOURCES` table) received since last successful run (default: last 24 hours)
3. For each email:
   - Extract text body
   - Extract PDF attachments
   - Determine source from sender domain
   - Parse listings using the appropriate per-source parser
   - For PDFs: use `pdfplumber` for extraction; if confidence < 70%, flag for review
4. Normalize each listing into the standard schema (see `LISTING SCHEMA`)
5. Deduplicate against `data/deals.db` using rules in `DEDUP LOGIC`
6. Score each new listing using the channel-appropriate scorer in `app/scorers/`
7. Insert/update database
8. Build the daily digest (top 5 per channel + overall top 10)
9. **Create a Gmail draft** addressed to `DIGEST_RECIPIENT`, with subject prefixed `[ATG-DIGEST-AUTOSEND]`. The Apps Script will send and unprefix it 5 minutes later.
10. Log run summary to `data/run_log.json`

---

## Project structure

```
atg-scanner/
├── CLAUDE.md                          # this file — execution instructions
├── README.md                          # human-readable setup guide
├── apps_script/
│   └── atg_digest_autosender.gs       # companion Apps Script (paste into script.google.com)
├── .env.example                       # template for secrets
├── pyproject.toml                     # Python 3.11+ dependencies
├── app/
│   ├── __init__.py
│   ├── main.py                        # entry point: run_daily_scan()
│   ├── config.py                      # source list, channel definitions, env loading
│   ├── gmail_client.py                # Gmail wrapper (uses built-in connector via MCP)
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py                    # Parser interface
│   │   ├── crexi.py
│   │   ├── loopnet.py
│   │   ├── sands_ig.py
│   │   ├── snyder_carlton.py
│   │   ├── b_and_e.py
│   │   ├── hanley.py
│   │   ├── matthews.py
│   │   ├── northmarq.py
│   │   ├── argus_storage.py
│   │   ├── storage_group.py
│   │   ├── skyview.py
│   │   ├── rv_storage_broker.py
│   │   ├── hayden_outdoors.py
│   │   ├── mewbourne.py
│   │   ├── aef.py
│   │   ├── energynet.py
│   │   ├── og_clearinghouse.py
│   │   ├── sol_systems.py
│   │   ├── energea.py
│   │   ├── levelten.py
│   │   ├── zenith_ios.py
│   │   ├── alterra.py
│   │   └── pdf_om.py                  # generic OM PDF parser using pdfplumber
│   ├── scorers/
│   │   ├── __init__.py
│   │   ├── base.py                    # Scorer interface
│   │   ├── msa_commercial.py
│   │   ├── carwash_nnn.py             # has structural gates
│   │   ├── self_storage.py
│   │   ├── oil_gas_wi.py
│   │   ├── solar.py
│   │   └── ios.py
│   ├── db.py                          # SQLite operations
│   ├── deduper.py                     # listing dedup logic
│   ├── digest.py                      # build the digest email + create draft
│   └── utils.py
├── data/
│   ├── deals.db                       # SQLite database
│   ├── attachments/                   # PDF attachments organized by date
│   └── run_log.json                   # historical run logs
└── tests/
    ├── fixtures/                       # sample broker emails + PDFs for testing
    └── test_*.py
```

---

## SOURCES (sender domain → channel mapping)

| Sender domain | Channel | Parser |
|---|---|---|
| `noreply@crexi.com` | routes by saved-search name in subject | `crexi.py` |
| `alerts@loopnet.com` | routes by saved-search name in subject | `loopnet.py` |
| `*@sandsig.com`, `*@signnn.com` | car_wash_nnn, ios | `sands_ig.py` |
| `eric.carlton@colliers.com`, `jereme.snyder@colliers.com` | car_wash_nnn | `snyder_carlton.py` |
| `*@tradenetlease.com` | car_wash_nnn | `b_and_e.py` |
| `*@hanleyinvestment.com` | car_wash_nnn | `hanley.py` |
| `*@matthews.com` | car_wash_nnn, msa_commercial | `matthews.py` |
| `*@northmarq.com` | car_wash_nnn | `northmarq.py` |
| `*@argus-selfstorage.com` | self_storage | `argus_storage.py` |
| `*@thestoragegroup.com` | self_storage | `storage_group.py` |
| `*@skyviewadvisors.com` | self_storage | `skyview.py` |
| `travis@rvstoragebroker.com` | self_storage (RV/boat sub) | `rv_storage_broker.py` |
| `*@haydenoutdoors.com` | self_storage (RV/boat sub) | `hayden_outdoors.py` |
| `*@mewbourne.com` | oil_gas_wi | `mewbourne.py` |
| `teresa@aec-kc.com`, `*@aefdyer.com` | oil_gas_wi | `aef.py` |
| `*@energynet.com` | oil_gas_wi | `energynet.py` |
| `*@ogclearinghouse.com` | oil_gas_wi | `og_clearinghouse.py` |
| `*@solsystems.com` | solar | `sol_systems.py` |
| `*@energea.com` | solar | `energea.py` |
| `*@leveltenenergy.com` | solar | `levelten.py` |
| `*@zenithios.com` | ios | `zenith_ios.py` |
| `*@alterraproperty.com` | ios | `alterra.py` |

**Channel routing for Crexi/LoopNet:** match the saved-search name in the email subject:
- "Self Storage National" → self_storage
- "Car Wash Fee Simple" → car_wash_nnn
- "Springfield Commercial" → msa_commercial
- "Industrial Outdoor Storage" → ios

---

## LISTING SCHEMA (normalized)

```python
@dataclass
class Listing:
    # Identity
    source: str                       # "crexi", "sands_ig", etc.
    source_listing_id: str | None
    channel: str
    listing_url: str | None
    email_id: str                     # Gmail message ID

    # Property basics
    title: str
    address: str
    city: str
    state: str
    zip: str | None

    # Financials
    price: int                        # USD
    cap_rate: float | None            # decimal (0.075 = 7.5%)
    noi: int | None
    sf: int | None
    lot_acres: float | None

    # Lease (NNN deals)
    tenant: str | None
    tenant_credit: str | None         # "public_corporate" / "private_large" / "private_small" / "franchisee"
    lease_type: str | None            # "absolute_nnn" / "nnn" / "nn" / "ground_lease"
    lease_start: date | None
    lease_expiration: date | None
    term_remaining_years: float | None
    escalator_pct: float | None       # annual equivalent
    roof_structure: str | None        # "tenant" / "landlord" / "shared"

    # Tax
    bonus_dep_eligible: bool | None
    estimated_cost_seg_pct: float | None

    # Metadata
    extraction_confidence: float
    needs_review: bool
    raw_data: dict
    first_seen: datetime
    last_seen: datetime
```

---

## DEDUP LOGIC

A listing is a duplicate of an existing one if ANY of these match:
1. Same `source` + same `source_listing_id` (exact match)
2. Same `address` (Levenshtein ≤ 5) AND `price` within 2%
3. Same `tenant` (NNN) + same `address` (Levenshtein ≤ 10) + price within 5%

When duplicate detected:
- Update `last_seen` timestamp
- If `price` changed >2%: log a `price_change` event
- Don't include in today's digest UNLESS the price drop is > 5% (triggers a price drop alert)

---

## SCORING

Scoring code is in `app/scorers/`. Each scorer implements:

```python
class Scorer:
    channel: str
    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        """Return (all_passed, list_of_failed_gate_names)."""
    def score(self, listing: Listing) -> ScoreResult:
        """Return ScoreResult with score 0-100 and breakdown."""
```

### Channel: car_wash_nnn

**Structural gates (ALL must pass; if any fail, listing rejected):**
1. `lease_type == "absolute_nnn"` — fee simple absolute NNN
2. `bonus_dep_eligible == True`
3. `roof_structure == "tenant"`
4. `lease_type != "ground_lease"`

**Weighted score (0-100):**
- Tenant credit (18): public=18, private_large=14, private_small=8, franchisee=5
- Lease term remaining (18): ≥18yr=18, ≥15yr=15, ≥10yr=8, ≥7yr=4, <7=0
- Cost seg potential (15): self-service=15, express tunnel=12, tunnel+light=10, full-service=8
- Cap rate vs market (12): ≥7%=12, 6.5-7%=9, 6-6.5%=6, <6%=3
- Rent escalator (12): ≥1.8%=12, 1.4-1.8%=9, 1-1.4%=6, <1%=2
- Y1 cash flow (10): calc from price (25% down, 7% rate, 25yr am); ≥$5k/mo=10, ≥$2k=8, ≥$0=5, ≥-$2k=2, <-$2k=0
- Deal size fit (8): $2-6M=8, $1.5-2M or $6-8M=6, else=3
- Brand strength (7): tier-1 (Mister, Take 5, Whistle, Tidal, Mammoth, Whitewater)=7, tier-2 (MOD, Quick Quack, Zips, Club)=5, else=3

**Verdict bands:** ≥80=PURSUE, 65-79=PURSUE_CONDITIONS, 50-64=WATCH, <50=PASS

### Channel: msa_commercial

**Filters (hard requirements):**
- State == "MO"
- County in [Greene, Christian, Webster, Taney]
- Price between $400k and $1.5M

**Weighted score (0-100):** Price/SF vs comp (20), Lease-up risk (20), Tenant credit (15), CoC at 25% down (15), Cost seg (10), Location (10), Building age/condition (10)

**Verdict bands:** ≥75=PURSUE, 60-74=WATCH, <60=PASS

### Channel: self_storage

**Filters:**
- Excludes CA, NY
- Price $1.5M-$5M
- Occupancy ≥70% OR clear value-add story

**Weighted score (0-100):** Cap rate (15), Cost seg yield (15) — RV/boat scores higher, Occupancy + market saturation (15), ATG operational synergy (10), Climate-controlled mix (8), Acres + expansion (10), Population growth 3mi (10), Asset age (10), CoC (7)

**Verdict bands:** ≥75=PURSUE, 60-74=WATCH, <60=PASS

### Channel: oil_gas_wi

**Filters:**
- Direct WI only (NOT funds)
- Investment $250k-$1.5M
- Excludes royalty-only

**Weighted score (0-100):** Operator credit (20): Mewbourne=20, Pioneer=18, Devon/EOG=18, mid=12, unknown=5; IDC % (15): ≥75%=15; Basin (12): Permian=12, Anadarko/Bakken=10; Decline curve (12); AFE accuracy (10); Min vs capacity (10); Hedging (8); ESG/political (7); Diversification (6)

**Verdict bands:** ≥75=PURSUE, 60-74=WATCH, <60=PASS

### Channel: solar

**Filters:**
- Operational only (not development)
- PPA term ≥15yr remaining
- Excludes residential rooftop, community solar

**Weighted score (0-100):** ITC + bonus dep stack (20), PPA counterparty credit (15), PPA term (15), Equipment age/warranty (12), Production data (12), Geographic risk (8), Regulatory (8), Cash yield (10)

**Verdict bands:** ≥75=PURSUE, 60-74=WATCH, <60=PASS

### Channel: ios

**Filters:**
- Price $2M-$5M
- Lot ≥2 acres usable
- Excludes vacant land speculation

**Weighted score (0-100):** Land/total ratio (15), Tenant in place (15), Lease structure (15), Logistics corridor (12), Zoning permanence (12), Acreage usable (10), Improvements (10), Cap vs market (8), Environmental (3)

**Verdict bands:** ≥75=PURSUE, 60-74=WATCH, <60=PASS

---

## DIGEST DRAFT FORMAT

ONE Gmail draft per run. Skip if no new listings AND no price drops.

**Subject pattern:** `[ATG-DIGEST-AUTOSEND] ATG Deal Digest — {Day, Mon DD} — {N} new, top score {X}/100`

The Apps Script will strip `[ATG-DIGEST-AUTOSEND]` before sending. Final delivered subject: `ATG Deal Digest — Tue Apr 28 — 23 new, top score 82/100`

**Body structure:** plain HTML, mobile-friendly. Sections in order:

```
1. OVERALL TOP 10 — across all channels, sorted by score desc
2. PRICE DROPS — listings whose price dropped >5% since last seen
3. CHANNEL: CAR WASH NNN — top 5
4. CHANNEL: MSA COMMERCIAL — top 5
5. CHANNEL: SELF-STORAGE + RV/BOAT — top 5
6. CHANNEL: OIL & GAS WORKING INTERESTS — top 5
7. CHANNEL: SOLAR FARMS — top 5
8. CHANNEL: INDUSTRIAL OUTDOOR STORAGE — top 5
9. SCAN STATS — emails processed, listings found, sources active
```

For each listing show: verdict + score, tenant + city, price + cap, top 3 score components, source + URL, broker contact. If a channel has no new deals, OMIT the section.

---

## SECRETS / .env

```
DIGEST_RECIPIENT=agrassi@ybpsrv.com
DIGEST_SENDER_NAME=ATG Deal Scanner
TIMEZONE=America/Chicago
DRAFT_MAGIC_PREFIX=[ATG-DIGEST-AUTOSEND]
FAILURE_ALERT_EMAIL=agrassi@ybpsrv.com
```

No SMTP credentials needed — Gmail connector + Apps Script handles delivery.

---

## EXECUTION GUIDANCE

When this routine fires:

1. **Read state first.** Open `data/run_log.json` for last successful run timestamp. Default to 24 hours ago if missing.
2. **Don't re-process.** Use Gmail's `after:` query operator with the last-run timestamp.
3. **Be resilient.** Parser failures log and skip; don't crash the run.
4. **Be honest about confidence.** PDF extraction confidence < 0.7 → flag `needs_review = True`, include in digest with `[NEEDS REVIEW]` tag.
5. **Idempotency.** Running twice in the same hour produces no duplicate drafts/rows.
6. **Always log.** Each run appends to `run_log.json`: timestamp, emails processed, listings found, listings new, listings updated, parser failures, draft created (Y/N).
7. **On total failure** (Gmail connector error): create a draft with subject `[ATG-DIGEST-AUTOSEND] ATG Scanner FAILURE — {date}` and a body explaining what failed. The Apps Script will send it. Don't skip silently.

---

## TESTING

`tests/fixtures/` includes the three OMs already on file:
- MOD Wash Bridgeville (expected: PURSUE_CONDITIONS, score 70-78)
- Quick Quack Murrieta (expected: STRUCTURAL_FAIL — ground lease)
- Mister American Fork (expected: PURSUE_CONDITIONS, score 68-75)

Each parser ships with a fixture + test that must pass before the parser is considered shipped.

---

## BUILD ORDER

**Phase 1: scaffolding (1 day)**
- pyproject.toml, .env.example, README.md
- SQLite schema + migration
- Listing dataclass + base Parser/Scorer interfaces
- Gmail connector wrapper (read inbox, fetch attachments, create drafts)
- main.py entry point that does nothing yet
- Test: routine fires, logs "hello world" run, no crashes

**Phase 1.5: Apps Script setup (30 min)**
- User pastes `apps_script/atg_digest_autosender.gs` into script.google.com
- User runs setupTrigger() once, grants permissions
- User runs createTestDraft() then sendAtgDrafts() to verify auto-send works
- This must be working BEFORE Phase 2 — otherwise we can't validate end-to-end

**Phase 2: PDF parser + car wash scorer (2 days)**
- pdfplumber-based PDF extractor (`pdf_om.py`)
- car_wash_nnn scorer with structural gates
- Test against 3 OMs on file: produces expected scores

**Phase 3: Crexi + Sands IG parsers + first digest (2 days)**
- Crexi alert email parser
- Sands IG broadcast parser
- Digest builder that creates the Gmail draft with magic prefix
- End-to-end test: forward sample emails, verify draft created, verify Apps Script sends it

**Phase 4: remaining parsers (3 days, batched)**
- All remaining sources from the SOURCES table
- Each parser ships with a fixture + test

**Phase 5: deploy as routine (1 day)**
- Verify entire flow runs locally
- Configure as Claude Code Routine: schedule daily 6:30am Central
- Verify Apps Script trigger is active for 6:35am Central
- Monitor first 5 runs daily; tune as needed

**Estimated total: 9 working days from start.**

---

## STATUS TRACKING

- [x] Phase 1: scaffolding
- [x] Phase 1.5: Apps Script installed and tested (per user, 2026-04-27)
- [ ] Phase 2: PDF parser + car wash scorer
- [ ] Phase 3: Crexi + Sands IG + first digest
- [ ] Phase 4: remaining parsers
- [ ] Phase 5: routine deployment
