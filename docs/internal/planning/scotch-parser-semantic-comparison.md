# scotch-parser v0.1: semantic tree capability comparison (edgartools 5.19 vs analyzed sec-parser)

## 1) Executive comparison (implementation-first)

- edgartools already has a production parser pipeline (`HTMLParser -> HTMLPreprocessor -> DocumentBuilder -> postprocessor`) with typed nodes and configurable strategies; this is a stronger base engine than reusing sec-parser architecture.  
- edgartools has explicit hybrid section detection (TOC-first, then heading, then pattern), while sec-parser analysis describes section detection mainly as regex + style pipelines.  
- edgartools has richer built-in form coverage in section patterns (10-K/10-Q/20-F/8-K) and includes issuer-specific cross-reference index handling (e.g., GE/Citigroup style filings).  
- edgartools table parsing is materially ahead of the analyzed sec-parser baseline: row/header inference, period header heuristics, and coarse table typing already exist.  
- sec-parser still contributes useful deterministic heuristics as *enrichment passes*: stable hierarchical IDs, sentence segmentation tuned for SEC abbreviations, prose-table stubs, and footnote linking.  
- sec-parser’s title-level weakness (first-style-wins) should **not** be imported; edgartools already uses multi-detector voting and confidence.  
- scotch-parser should treat edgartools `Document/Node` output as the canonical base tree, then apply idempotent enrichment passes that only add metadata/new nodes, never mutate raw source text.  
- Keep current sanitize/stamp baseline; only add minimal optional deltas where evidence anchoring requires finer granularity (table cells and footnote markers).  
- Highest ROI now is not “new parser logic”; it is deterministic post-parse enrichment and sidecar generation that maps node IDs to stamped DOM anchors.  
- For v0.1, avoid ML-dependent classification; keep everything regex/style/position/statistics-based so artifacts are reproducible for diffing.  
- For downstream reader + card pipeline, the key missing artifact is a strong `sidecar.json` (TOC hierarchy, node paths, table metadata, diagnostics, anchor locators).  
- Recommendation: do **not** copy sec-parser pipeline classes; reimplement only selected heuristics as small pure functions/passes under `packages/scotch-parser/`.

## 2) Gap & steal list

| Heuristic / concept from sec-parser analysis | Category | edgartools 5.19 status | Steal? | scotch-parser pass (if YES) | Inputs | Deterministic rules | Outputs | Risks/failure mode | Minimal tests |
|---|---|---|---|---|---|---|---|---|---|
| Stable hierarchical IDs (`TopSection -> Title -> text index`) | Item boundary / normalization | **Partially covered** (sections exist, but no global stable IR ID contract for every node/sentence/table cell) | YES | `assign_semantic_ids_pass` | Parsed node tree + stamped DOM map | Canonical slug + ordinal scheme per parent; never use runtime object identity | `node_id`, `parent_id`, `path`, `dom_locator` | ID churn if sibling ordering changes unexpectedly | (1) Re-run deterministic id assignment twice on same doc => byte-identical IDs. (2) Insert unrelated node in another branch => unaffected branch IDs unchanged. |
| Two-pass heading level scoring by style rank | Heading detection hierarchy | **Already covered / better covered** (multi-detector + confidence voting) | NO | — | — | — | — | sec-parser approach can regress on styled disclaimers | N/A |
| Regex-hardening for Part/Item boundary normalization | Item boundary / normalization | **Partially covered** (header patterns + form-specific section extractor) | YES | `item_header_normalization_pass` | Heading nodes + section names | Normalize variants (`ITEM 1A`, `Item 1A.`, punctuation/em dash noise), map to canonical `item_1a` | Canonical item metadata on nodes + diagnostics | False positives from inline references | (1) Main header `ITEM 7—...` normalizes to `item_7`. (2) Sentence "See Item 7" does not become section header. |
| Introductory/pre-item bucket | Item boundary / normalization | **Partially covered** (sections exist, but pre-item explicit bucket not first-class in IR) | YES | `intro_bucket_pass` | Ordered top-level nodes + first item boundary | Everything before first canonical part/item tagged `introductory` | Synthetic Intro node + member references | Misclassify if filing has missing item headers | (1) Filing with cover + TOC + item headers => intro captured. (2) Filing starting directly with Item 1 => empty intro node absent. |
| Block merge across irrelevant/page artifacts | Block segmentation | **Partially covered** (postprocessor has cleanup; legacy merger ideas exist) | YES | `block_coalescing_pass` | Paragraph/text blocks + artifact markers | Merge adjacent text blocks separated only by page number/header noise | Fewer, larger `Block` nodes with provenance list | Over-merge across real headings | (1) `para + page# + para` merges. (2) `para + heading + para` does not merge. |
| Sentence boundary detection with SEC abbreviations | Block segmentation | **Not covered as required output artifact** | YES | `sentence_split_pass` | Clean block text + optional abbreviation list | pysbd/custom rules: protect `Inc.`, `No.`, `U.S.`, note refs `No. 3` | `Sentence` nodes with `sentence_id`, `section_id` | Split errors around legal abbreviations | (1) `Apple Inc. reported...` stays one sentence split point correct. (2) `See Note 3. Revenue...` not split after `Note 3.` incorrectly. |
| Table type classification (financial / TOC / exhibit / layout / reference) | Table extraction | **Partially covered** (`TableProcessor._detect_table_type` exists but coarse) | YES | `table_type_refinement_pass` | TableNode + local context blocks/headers | Use caption/header keywords + numeric density + nearby section labels | Refined `table_type`, confidence, reason codes | Borderline tables misclassified | (1) Balance-sheet style table => `financial_statement`. (2) index/page table => `toc`. |
| Prose-table context classifier (stub vs substantive) | Table extraction | **Not covered** | YES | `table_context_linking_pass` | Table node + prev/next text blocks | Detect stub cues (`see table below`, `following table`) vs substantive context length/content | `context_mode` (`stub`, `substantive`, `mixed`) + linked block IDs | Boilerplate phrases may be ambiguous | (1) Short reference phrase marked `stub`. (2) Multi-sentence discussion with figures marked `substantive`. |
| Table caption vs heading disambiguation | Table normalization | **Partially covered** | YES | `table_caption_disambiguation_pass` | Heading + immediate following table | If short heading directly precedes table and matches caption-like pattern, relabel as table caption | Heading demoted; table caption set | Can hide real subsection heading | (1) "Table 1..." before table => caption. (2) "Risk Factors" before table remains heading. |
| TOC table detection improvements (Pg./PAGE variants, structure cues) | Table extraction | **Partially covered** (TOC analyzer exists) | YES | `toc_table_strengthening_pass` | Table text matrix + anchor links | Case-insensitive page token + row pattern (`Item + page#`) + link density | Table tagged `toc_candidate`, score | TOC-like exhibit lists false positives | (1) TOC with `Pg.` detected. (2) Non-TOC numeric table rejected. |
| Footnote marker + body linking | Footnote detection/linking | **Partially covered** (ix footnotes extractable, but semantic node linking to prose/table refs is limited) | YES | `footnote_linking_pass` | DOM anchors + stamped ids + text/table cells | Match superscript markers to footnote blocks by normalized symbol/number order and local scope | `Footnote` nodes + backlinks from refs | Duplicate symbols reused per table | (1) Numeric superscript links to matching footnote text. (2) Asterisk markers with table-local scope link correctly. |
| Cross-reference detection (`see Note X`, `Item Y`) | Other high leverage | **Partially covered** (ranking utilities have pattern detection, not sidecar link graph output) | YES | `cross_reference_graph_pass` | Sentence nodes + section map + table/footnote index | Regex patterns resolve to canonical section/node IDs where available | `cross_refs[]` edges in sidecar | Ambiguous references without target | (1) `see Item 7` resolves to `item_7`. (2) unresolved target emits diagnostic only. |
| Page header/page number statistical filtering | Block segmentation | **Partially covered** (builder has page-number filtering heuristics) | NO for v0.1 | — | — | Already in base; add only if regressions observed | — | Duplicate logic can conflict with base parser cleanup | N/A |
| Exhibit boundary classifier | Known patterns | **Partially covered** (8-K/10-Q section patterns include exhibits) | LATER | `exhibit_boundary_pass` | Section headings + regex in tail | `EXHIBIT X.X` boundary + materiality rules | Exhibit subtree metadata | Filing-specific edge cases | (1) 99.1 marked material. (2) 31/32 marked boilerplate. |
| Structural boilerplate hash lookup | Other | **Not covered in parser core** | NO for v0.1 | — | — | Better as downstream service over sentence corpus | — | Asset maintenance burden | N/A |
| Parsed output caching by content hash | Other | **Partially covered** (cache infra exists, but sidecar/artifact cache for scotch not defined) | YES (later) | `artifact_cache_pass` | html hash + config hash | deterministic key for semantic tree + sidecar | cache hit/miss metadata | stale cache if versioning weak | (1) same input/config => hit. (2) config change => miss. |
| Issuer-specific cross-reference index parsing (GE/Citigroup style) | Special issuer handling | **Already covered** (`cross_reference_index.py`) | NO (reuse edgartools directly) | — | — | Use existing detection/parser as upstream signal | — | Reimplementation risk with no added value | N/A |

## 3) Priorities

### Top 5 steals for v0.1 (highest ROI for reader + card pipeline)

1. `assign_semantic_ids_pass` (enables stable node/sentence/table references and diffability).  
2. `sentence_split_pass` (required for card inputs and parquet/duckdb sentence store).  
3. `table_context_linking_pass` (improves reader UX and avoids duplicate prose/table cards).  
4. `table_type_refinement_pass` (better table UX routing and indexing).  
5. `footnote_linking_pass` (high-signal accounting context; critical for evidence provenance).  

### Next 5 later

1. `cross_reference_graph_pass`  
2. `table_caption_disambiguation_pass`  
3. `toc_table_strengthening_pass`  
4. `item_header_normalization_pass`  
5. `exhibit_boundary_pass`  

### Explicit do-not-steal (for now)

- sec-parser architecture/pipeline framework itself.  
- first-occurrence style ranking for heading levels.  
- parser-embedded boilerplate-hash asset management.  
- any non-deterministic/ML-first classification in core parsing path.

## 4) Minimal sanitize/stamp deltas required?

Baseline answer: **mostly no changes required** for first pass implementation.

Recommended minimal deltas (optional flags, default OFF):

1. **Table evidence granularity delta (smallest possible):** in stamping, add optional cell stamping (`td`, `th`) only when `--stamp-table-cells` is enabled.  
   - Why: `footnote_linking_pass` and `table_context_linking_pass` need precise table-cell provenance for sidecar locators.  
   - Minimality: do not alter existing table-level stamping behavior; add separate opt-in branch.

2. **Footnote anchor delta (smallest possible):** in stamping, add optional stamp to superscript/reference-like inline nodes (`sup`, small anchor refs) outside script/table exclusions when `--stamp-footnote-refs` is enabled.  
   - Why: deterministic `ref -> footnote` linking requires stable anchors on both ends.  
   - Minimality: no sanitizer rewrite, no global inline stamping.

No sanitize changes are required to implement the top-5 passes listed above unless a specific filing class shows unresolved unsafe inline URI/style artifacts beyond current sanitizer scope.

## 5) Implementation plan (`packages/scotch-parser/`)

```text
packages/scotch-parser/
  pyproject.toml
  scotch_parser/
    __init__.py
    pipeline.py                  # orchestrates parse + passes
    models/
      ir_nodes.py                # Document/Item/Heading/Block/Sentence/Table/Cell/Footnote
      sidecar.py                 # sidecar schema dataclasses
    adapters/
      edgartools_adapter.py      # parse_html + section/table/headings extraction adapters
      stamping_adapter.py        # map data-src-id anchors into locator index
    passes/
      assign_semantic_ids.py
      sentence_split.py
      table_type_refinement.py
      table_context_linking.py
      footnote_linking.py
      cross_reference_graph.py   # later
      item_header_normalization.py # later
    serializers/
      sidecar_json.py
      parquet_writer.py
      duckdb_writer.py
    diagnostics/
      quality_metrics.py
      rule_trace.py
  tests/
    fixtures/
      filings/
    test_assign_semantic_ids.py
    test_sentence_split.py
    test_table_context_linking.py
    test_table_type_refinement.py
    test_footnote_linking.py
```

### Sequencing

1. **Acquire + sanitize + stamp** (existing external scripts stay authoritative).  
2. **Base parse via edgartools** (`edgar.documents.parse_html`) and extract sections/headings/tables from `Document`.  
3. **Build initial IR tree** (`Document -> Item/Heading/Block/Table`).  
4. **Run enrichment passes in fixed order:**  
   `item_header_normalization (later)` -> `assign_semantic_ids` -> `table_type_refinement` -> `table_context_linking` -> `footnote_linking` -> `sentence_split` -> `cross_reference_graph (later)`.
5. **Emit artifacts:** `semantic_tree.json`, `sidecar.json`, sentence parquet/duckdb.

### How to call edgartools as base engine

- Use `parse_html(html, config)` once.  
- Consume:
  - `document.sections` for Item/Part boundaries  
  - `document.headings` for hierarchy candidates  
  - `document.tables` for table nodes and metadata  
  - `document.text()` only for fallback diagnostics, not as primary structural source

### Validation/scoring loop

Compute deterministic metrics per filing and fail pipeline if thresholds breached:

- `% blocks with node_id` (target 100%)
- `% sentences with parent block_id + section_id` (target 100%)
- table typing coverage (non-`general` share)
- footnote link precision on golden fixtures
- unresolved cross-reference rate
- anchor resolution rate (`node_id -> data-src-id`)

### Mapping IR node ids to DOM anchors

- Primary key: stamped `data-src-id` map built from stamped HTML.  
- For each IR node, store:
  - `primary_locator`: best `data-src-id`  
  - `fallback_locator`: xpath/css path  
  - `source_offsets`: optional char offsets within block text  
- Table/Cell and Footnote nodes use optional stamping deltas only when enabled; otherwise attach table-level locator and diagnostic `locator_granularity=table`.

## 6) Test plan (fixtures + metrics)

### Fixtures to add

- 10-K with classic TOC + normal Item headings  
- 10-Q with repeated item numbers across Part I/II  
- 10-K with dense financial tables and superscript footnotes  
- issuer with cross-reference index style (GE/Citigroup-like)  
- filing with page header/footer artifacts in middle of section

### Programmatic checks

- Determinism check: run full pipeline twice, compare `sidecar.json` hash.
- ID stability check under irrelevant node insertion fixture.
- Sentence splitter regression suite for SEC abbreviation edge cases.
- Table context confusion matrix (`stub` vs `substantive`) on labeled fixtures.
- Footnote link exact-match accuracy and unresolved-link diagnostics.
- Section hierarchy integrity: every sentence must resolve to exactly one section path.
