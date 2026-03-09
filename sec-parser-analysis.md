# scotch-parser Roadmap

**Fork of:** [alphanome-ai/sec-parser](https://github.com/alphanome-ai/sec-parser)
**Scope:** US-listed entities, English-only filings, 2015+ (inline CSS era).
**Current support:** 10-K, 10-Q. Expansion planned for 8-K, DEF 14A, S-1.

---

## 1. Vision

scotch-parser is the **structural parsing module** in a larger SEC filing analysis pipeline. It takes raw SEC filing HTML and produces a fully addressed, hierarchically structured document — every element (paragraph, title, table, image) identified by type, assigned a stable segment ID, and placed in a navigable tree.

The parser serves two downstream consumers:

1. **NLP Pipeline** — Extracts every sentence from a filing with provenance (segment address). Downstream layers label each sentence for signal (`is_boilerplate`, `has_signal: low|medium|high`) and tag with business drivers (revenue, concentration risk, KPI metrics, etc.) against a predetermined ontology. An LLM constructs evidence cards that synthesize fact-spans and surface mechanical insights (accounting changes, timing shifts, mix effects). The parser's job is to deliver clean, addressed, structurally segmented text — not to perform the labeling or synthesis.

2. **Reflowed Reader** — A modern SEC filing reading experience with proper typography, scrollable tables, intelligent TOC navigation, and Intersection Observer-driven active-section tracking. The parser provides the structural backbone: the semantic tree powers the TOC, element types drive rendering components, and section boundaries enable scroll-position mapping.

A separate numeric pipeline (edgartools) handles XBRL fact extraction and financial statement/KPI processing. scotch-parser does not duplicate that work.

---

## 2. Goals

| # | Goal | Description | Primary Consumer |
|---|------|-------------|-----------------|
| G1 | **Segment-Addressed Text Extraction** | Every element gets a stable, hierarchical `segment_id` (e.g., `part2item7:revenue_recognition:text_3`). All text is extractable with its structural address for full provenance. | NLP Pipeline |
| G2 | **Smart TOC & Navigation** | A serializable Table of Contents data structure with section IDs, hierarchy levels, and section boundaries. Powers a floating pill UI with Intersection Observer (idle/scroll/hover states, section-jump, progress-within-section). | Reflowed Reader |
| G3 | **Complete Table Inventory** | Identify and classify every table by purpose: financial statement, footnote, layout, TOC, schedule, exhibit. For non-XBRL tables, capture surrounding prose as context. | Both |
| G4 | **Prose-Table Relationship** | For each table, determine whether surrounding prose is substantive context (keep) or a stub reference like "refer to the table below" (discard prose, present table only). | Reflowed Reader |
| G5 | **Diff-Ready Output** | Normalized, segment-addressed text and table output suitable for text-diffing (prose changes across periods) and number-diffing (financial figure changes across periods). | NLP Pipeline |
| G6 | **Sentence-Level Segmentation** | Split each text element into individual sentences with inherited segment IDs (e.g., `part2item7:revenue_recognition:text_3:s2`). Filing-aware boundary detection handles SEC-specific abbreviations ("Inc.", "No.", "vs.", note references). | NLP Pipeline |
| G7 | **Cross-Reference Linking** | Detect intra-document references ("see Note 5", "as described in Item 7") and produce link targets using segment IDs. | Reflowed Reader |
| G8 | **Multi-Filing-Type Support** | Extend parsing beyond 10-K/10-Q to 8-K, DEF 14A, and S-1 filing types with appropriate section definitions and pipeline adjustments. | Both |
| G9 | **Rendering Hint Metadata** | Expose typography and layout hints (scrollable table thresholds, bold/italic/uppercase as rendering directives, table row counts) so the reader can apply proper typography rather than raw inline CSS. | Reflowed Reader |

---

## 3. Scope: What the Parser Does and Does Not Do

### In Scope (scotch-parser responsibilities)

| Responsibility | Detail |
|---------------|--------|
| **HTML structural parsing** | Parse SEC filing HTML into typed semantic elements (titles, text, tables, images, sections). |
| **Section detection** | Identify Part/Item boundaries for all supported filing types. |
| **Hierarchical tree construction** | Build a navigable parent-child tree from the flat element list using composable nesting rules. |
| **Stable element addressing** | Assign deterministic `segment_id` to every element for provenance and cross-period alignment. |
| **TOC data structure** | Produce a serializable TOC with section IDs, hierarchy, and boundary data. |
| **Sentence segmentation** | Split text elements into sentences with inherited segment IDs, using filing-aware boundary detection. |
| **Table classification** | Classify tables by purpose (financial statement, footnote, layout, TOC, etc.). |
| **Prose-table relationship** | Determine whether prose adjacent to a table is substantive or a stub reference. |
| **Text normalization** | Collapse whitespace, strip page artifacts, normalize quotes/dashes for diff-ready output. |
| **Cross-reference detection** | Identify "see Note X" / "as described in Item Y" patterns and produce link targets. |
| **Rendering hints** | Expose text style properties, table metrics, and layout metadata for frontend rendering. |
| **Boilerplate flagging (structural)** | Use statistical methods (repeated text across filing, identical to prior period) to flag likely boilerplate at the element level. This is cheap and deterministic — no LLM needed. |
| **HTML pre-processing** | Normalize messy SEC HTML (non-breaking spaces, nested empty tags, `<font>` tags, inconsistent `<br>` vs `<p>`) before parsing. |

### Out of Scope (downstream pipeline responsibilities)

| Responsibility | Owner | Detail |
|---------------|-------|--------|
| **Ontology definition** | NLP Pipeline | The taxonomy of business drivers (revenue, concentration risk, KPI metrics, etc.) is defined and maintained outside the parser. |
| **Sentence labeling** | NLP Pipeline | `is_boilerplate`, `has_signal`, and business driver tags are applied by downstream LLM/ML layers using the parser's addressed output. |
| **Evidence card construction** | NLP Pipeline | Synthesizing fact-spans into cards with mechanical insights is an LLM task consuming parser output. |
| **Insight generation** | NLP Pipeline | Surfacing accounting, timing, and mix insights from labeled sentences is downstream analysis. |
| **XBRL fact extraction** | edgartools | Tagged financial facts, line items, and dimensional data are handled by edgartools. |
| **Financial statement parsing** | edgartools | Structured extraction of income statements, balance sheets, cash flows into dataframes. |
| **KPI / metric extraction** | edgartools | Numeric processing of financial metrics from XBRL-tagged data. |
| **Frontend rendering** | Reflowed Reader | The reader app consumes the parser's tree, TOC, and rendering hints but owns all UI/UX. |
| **LLM inference** | NLP Pipeline | All model calls for classification, summarization, or synthesis happen outside the parser. |

### Boundary Principle

The parser produces **structure, addresses, and metadata**. It does not produce **judgments, labels, or analysis**. The one exception is structural boilerplate detection (repeated identical text), which is statistical and deterministic.

---

## 4. Filing Type Expansion Strategy

### Priority Order

| Filing Type | Effort | Value | Rationale |
|------------|--------|-------|-----------|
| **8-K** (Current Reports) | Moderate | High | Event-driven disclosures (CEO departures, restatements, acquisitions, covenant breaches). Highest signal density per page. Defined item structure (Items 1.01–9.01) with two-decimal format. Variable item sets per filing. Needs `FilingSectionsIn8K` and `TopSectionManagerFor8K` with relaxed matching. Most pipeline steps work as-is. |
| **DEF 14A** (Proxy Statements) | High | High | Executive compensation tables, shareholder proposals, governance disclosures. Rich NLP content but complex structure — doesn't follow rigid Part/Item format. Nested exhibits. Requires significant new section detection heuristics. |
| **S-1 / S-3** (Registration Statements) | Moderate | Medium | Similar Part/Item structure to 10-K with additional sections (Use of Proceeds, Dilution, etc.). Valuable for IPO analysis. Straightforward to add after 8-K. |
| **13-F** (Institutional Holdings) | Low | Low | Essentially one big table of holdings. The interesting parsing is already handled by edgartools. Deprioritize unless cover page narrative extraction is needed. |

### Implementation Pattern for New Filing Types

Each new filing type requires:
1. A `FilingSectionsInXX` definition in `top_section_title_types.py`
2. A `TopSectionManagerForXX` subclass with appropriate regex patterns
3. A `EdgarXXParser` subclass in `core.py` with its step configuration
4. Section-specific test fixtures and accuracy benchmarks

---

## 5. Additions & New Capabilities

### 5.1 Sentence Boundary Detection

**Recommendation:** Integrate [spaCy](https://spacy.io/) with a custom `sentencizer` component tuned for SEC filings.

**Why spaCy over naive splitting:**
- SEC filings contain dense abbreviations that break naive regex splitting: "Inc.", "No.", "vs.", "Reg.", "approx.", "Corp.", "Ltd.", "Jr.", "Sr."
- Note references ("see Note 5.") are not sentence ends in context
- Legal citations ("Section 13(a) of the Exchange Act") contain periods that aren't boundaries
- Table stub sentences end with colons, not periods

**Implementation approach:**
- Add spaCy as an optional dependency (sentence segmentation is opt-in)
- Create a `SentenceSegmenter` processing step that runs after `TextElementMerger`
- Use spaCy's `en_core_web_sm` model with a custom rule-based `sentencizer` pipeline component that adds SEC-specific abbreviation exceptions
- Each sentence gets the parent element's `segment_id` plus `:s{index}` suffix
- Produce `SentenceElement` objects (new type) as children of the parent `TextElement`
- Fallback: if spaCy is not installed, provide a regex-based splitter with known limitations

**Alternative considered:** [pySBD](https://github.com/nipunsadvilkar/pySBD) (Python Sentence Boundary Disambiguation). Lighter than spaCy, rule-based, handles abbreviations well. Could be the better choice if we want to avoid the spaCy dependency weight. Worth prototyping both.

### 5.2 HTML Pre-Processing / Normalization

**Problem:** SEC filings have notoriously messy HTML — non-breaking spaces (`&nbsp;`) everywhere, nested empty `<span>` tags, `<font>` tags with inline styles, inconsistent `<br>` vs `<p>` usage, invisible zero-width characters.

**Implementation:** Add an `HtmlNormalizer` that runs before `HtmlTagParser`:
- Collapse multiple `&nbsp;` into single spaces
- Strip empty wrapper elements (`<span></span>`, `<font></font>`, `<div></div>`) that add no styling
- Normalize `<br/><br/>` sequences to `<p>` boundaries
- Strip zero-width characters and other invisible Unicode
- Preserve all attributes and styles on elements that carry them

### 5.3 Structural Boilerplate Detection

**Problem:** Boilerplate sentences (risk factor disclaimers, safe harbor statements, standard legal text) appear identically across filings and across periods. Detecting these statistically is cheap and accurate — no LLM needed.

**Implementation approach (two layers):**
- **Cross-filer frequency:** Hash each sentence (after normalization). Maintain a frequency table across a corpus. Sentences appearing in >N filings from different CIKs are boilerplate. This runs offline to build the hash table; the parser just looks up each sentence.
- **Same-filer period-over-period:** Compare sentences between the current filing and the prior period for the same filer. Identical sentences are "unchanged boilerplate." Changed sentences are higher-signal.

**Parser responsibility:** The parser provides normalized, addressed sentences. Boilerplate detection is a lookup table operation on that output. The parser *could* ship with a pre-built boilerplate hash table as a data asset, or this can live entirely downstream.

### 5.4 Footnote Detection and Numbering

SEC filings contain extensive footnotes to financial statements (Note 1 through Note 20+). These are structurally distinct — subsections within Item 8, each with a numbered title and content.

**Implementation:**
- Add a `FootnoteClassifier` step that recognizes "Note N" or "NOTE N" patterns within financial statement sections
- Produce `FootnoteElement` (new type) with a `.note_number` attribute
- Improves TOC (footnotes listed as collapsible children of Item 8)
- High-value for NLP pipeline (footnotes contain dense, high-signal content about accounting policies, contingencies, and segment data)

### 5.5 Exhibit Boundary Detection

Filings end with exhibits (certifications, consent letters, press releases). Most are boilerplate but some (Exhibit 99.1 in 8-Ks — earnings press releases) contain material content.

**Implementation:**
- Add an `ExhibitClassifier` step that detects exhibit boundaries ("EXHIBIT X.X", "Exhibit Index")
- Classify as material vs. boilerplate based on exhibit number conventions
- Allows the reader to collapse/hide boilerplate exhibits while surfacing material ones

### 5.6 Parsed Output Caching

**Problem:** Re-parsing the same filing during dev iteration or ontology updates is wasteful.

**Implementation:** Content-hash-based cache. The tree is deterministic given the same HTML input and pipeline configuration. Store serialized `SemanticTree` keyed by `hash(html_content + pipeline_config_hash)`. Avoid re-parsing on cache hit.

---

## 6. Library Review

### 6.1 Architecture Overview

The library follows a **Pipeline + Strategy** pattern:

```
Raw HTML
  → HtmlTagParser (BeautifulSoup4 wrapper)
    → Flat list of HtmlTag objects
      → 14-step sequential processing pipeline
        → Each step classifies/reclassifies elements
          → Flat list of typed AbstractSemanticElement
            → TreeBuilder (stack-based, composable nesting rules)
              → SemanticTree of TreeNode objects
```

**Key architectural properties:**
- Each element starts as `NotYetClassifiedElement` and is progressively reclassified
- Steps are composable: injectable, replaceable, orderable via `get_steps` callable
- `_NUM_ITERATIONS` enables multi-pass behavior per step (used for statistical steps)
- `types_to_process` / `types_to_exclude` filters scope each step precisely
- Errors are non-fatal: caught per-element as `ErrorWhileProcessingElement`
- `CompositeSemanticElement` handles mixed-content containers (prose + table in one tag)
- `HtmlTag` caching layer makes repeated access O(1) over immutable HTML

**Dependencies:** BeautifulSoup4, lxml, pandas, loguru, cssutils, xxhash, frozendict.

### 6.2 Semantic Element Type System

```
AbstractSemanticElement
 ├── NotYetClassifiedElement
 ├── ErrorWhileProcessingElement
 ├── IrrelevantElement
 │   ├── EmptyElement
 │   ├── PageNumberElement
 │   ├── PageHeaderElement
 │   └── IntroductorySectionElement
 ├── TextElement (with DictTextContentMixin)
 ├── SupplementaryText (with DictTextContentMixin)
 ├── ImageElement
 ├── HighlightedTextElement (carries TextStyle)
 ├── TitleElement (AbstractLevelElement, with level: int)
 ├── TopSectionStartMarker (AbstractLevelElement, with section_type: TopSectionInFiling)
 │   └── TopSectionTitle (also has DictTextContentMixin)
 ├── TableElement
 │   └── TableOfContentsElement
 └── CompositeSemanticElement (container with inner_elements tuple)
```

Every element exposes: `.text`, `.html_tag`, `.get_source_code()`, `.get_summary()`, `.to_dict()`, `.processing_log`, `.contains_words()`, `.create_from_element()`.

### 6.3 The 14-Step Processing Pipeline

| # | Step Class | What It Does | Quality | Goal Relevance |
|---|-----------|--------------|---------|----------------|
| 1 | `IndividualSemanticElementExtractor` | Splits mixed-content containers into `CompositeSemanticElement` | Good | G3, G4 |
| 2 | `ImageClassifier` | Detects `<img>` tags → `ImageElement` | Fine | — |
| 3 | `EmptyElementClassifier` | Tags empty elements as `EmptyElement` (filtered from output) | Fine | G1 |
| 4 | `TableClassifier` | Tags `<table>` with >1 row as `TableElement` | Functional, needs enhancement | G3 |
| 5 | `TableOfContentsClassifier` | Reclassifies `TableElement` to `TableOfContentsElement` if "page" found in cells | Too simplistic | G2, G3 |
| 6 | `TopSectionManagerFor10Q/10K` | Two-pass regex match for "Part [I-IV]" and "Item [N]" | Core value-add, some brittleness | G1, G2 |
| 7 | `IntroductorySectionElementClassifier` | Marks everything before "Part 1" as `IntroductorySectionElement` | Fine | G1 |
| 8 | `TextClassifier` | Catch-all: remaining elements with text become `TextElement` | Fine | G1 |
| 9 | `HighlightedTextClassifier` | Analyzes inline CSS → `HighlightedTextElement` with `TextStyle` | Good for 2015+ | G2, G9 |
| 10 | `SupplementaryTextClassifier` | Reclassifies parenthetical text, italic notes, "accompanying notes" refs | Too narrow | G4 |
| 11 | `PageHeaderClassifier` | Statistical: short text appearing 5+ times → `PageHeaderElement` | Clever, effective | G1 |
| 12 | `PageNumberClassifier` | Statistical: digit-bearing short text appearing 5+ times → `PageNumberElement` | Clever, effective | G1 |
| 13 | `TitleClassifier` | Converts `HighlightedTextElement` → `TitleElement` with hierarchy level | Fragile — core concern | G1, G2 |
| 14 | `TextElementMerger` | Merges adjacent `TextElement` separated by `IrrelevantElement` gaps | Important for XBRL text | G1, G5 |

### 6.4 Tree Builder

Stack-based algorithm with three default nesting rules:
1. `AlwaysNestAsParentRule(TopSectionStartMarker)` — Part/Item sections parent everything
2. `AlwaysNestAsParentRule(TitleElement, exclude_children={TopSectionStartMarker})` — Titles parent non-title content
3. `NestSameTypeDependingOnLevelRule()` — Same-type elements nest by level

**Strengths:** Composable rule system, depth-first iteration, ASCII rendering for debugging.
**Gaps:** No section boundary data, no TOC serialization, no query/filter APIs, destructive stack popping.

### 6.5 Section Definitions

`TopSectionInFiling` dataclass: `identifier`, `title`, `order`, `level`.
- 10-Q: 12 sections (Part I Items 1–4, Part II Items 1–6, plus Part headings)
- 10-K: 27 sections (Part I–IV, Items 1–16 including 1c Cybersecurity)

### 6.6 Table Features

- **Detection:** `TableClassifier` + `TableCheck`
- **Metrics:** `get_approx_table_metrics()` → `ApproxTableMetrics(rows, numbers)`
- **Markdown:** `TableToMarkdown.convert()` — unmerges `colspan`, parses via `pd.read_html`
- **DataFrame:** `TableParser.parse_as_df()` — naive, parses only first table
- **TOC detection:** `check_table_contains_text_page()` — exact match only
- **Summary:** `TableElement.get_summary()` — has f-string bug (see Flaws)

### 6.7 Text Style Analysis

`TextStyle` frozen dataclass: `is_all_uppercase`, `bold_with_font_weight`, `italic`, `centered`, `underline`. All derived from inline CSS with 80% threshold. Adequate for 2015+ filings. Thresholds not configurable.

### 6.8 Function-by-Function Assessment

#### Tier 1: Critical (use and enhance)

| Function / Class | File | Status |
|-----------------|------|--------|
| `TreeBuilder.build()` | `tree_builder.py` | Needs enhancement: no section boundary data, no TOC output, stack-popping bug |
| `TopSectionManager._process_element()` | `top_section_manager.py` | Needs enhancement: regex brittleness, formatting variant intolerance, dead code |
| `TopSectionTitle` + `TopSectionStartMarker` | `top_section_title.py`, `top_section_start_marker.py` | Usable as-is. `.section_type.identifier` is a natural segment address root |
| `TitleClassifier._process_element()` | `title_classifier.py` | Needs fix: order-of-first-occurrence level assignment is fragile |
| `TableClassifier._process_element()` | `table_classifier.py` | Needs enhancement: no table type classification |
| `IndividualSemanticElementExtractor` | `individual_semantic_element_extractor.py` | Good as-is for splitting mixed containers |
| `AbstractSemanticElement.text` / `.get_source_code()` | `abstract_semantic_element.py` | Usable. Needs normalized text output for diffing |
| `SemanticTree.nodes` | `semantic_tree.py` | Usable as-is |
| `CompositeSemanticElement.unwrap_elements()` | `composite_semantic_element.py` | Usable as-is |

#### Tier 2: Important Supporting (minor modifications)

| Function / Class | File | Status |
|-----------------|------|--------|
| `HighlightedTextClassifier._process_element()` | `highlighted_text_classifier.py` | Good for 2015+ filings |
| `TextStyle.from_style_and_text()` | `highlighted_text_element.py` | Good. Make thresholds configurable |
| `PageHeaderClassifier._process_element()` | `page_header_classifier.py` | Good. Statistical approach is robust |
| `PageNumberClassifier._process_element()` | `page_number_classifier.py` | Good. Same statistical approach |
| `TextElementMerger._process_elements()` | `text_element_merger.py` | Important for XBRL-split text fragments |
| `SupplementaryTextClassifier._process_element()` | `supplementary_text_classifier.py` | Too narrow for general stub detection |
| `HtmlTag` (entire class) | `html_tag.py` | Good. Needs byte/character offset exposure |

#### Tier 3: Usable but Low Priority

| Function / Class | File | Status |
|-----------------|------|--------|
| `ImageClassifier` | `image_classifier.py` | Fine as-is |
| `TableElement.table_to_markdown()` | `table_element.py`, `table_to_markdown.py` | Usable for diff-friendly table output |
| `TableOfContentsClassifier` | `table_of_contents_classifier.py` | Too simplistic to rely on |
| Processing log system | `processing_log.py` | Fine as-is |
| Nesting rules | `nesting_rules.py` | Good composable design |

#### Tier 4: Low Value / Needs Replacement

| Function / Class | File | Why Low Value |
|-----------------|------|---------------|
| `TableParser.parse_as_df()` | `table_parser.py` | Parses only first table, naive headers, fragile `$`/`%` merging |
| `get_approx_table_metrics()` | `approx_table_metrics.py` | Rough row/number counts only; insufficient for table classification |
| `check_table_contains_text_page()` | `table_check_data_cell.py` | Exact-match only, misses common variants |
| `ParsingOptions` | `types.py` | Single field (`html_integrity_checks`). Severely underutilized |

---

## 7. Flaws

### Major Flaws

#### M1. Title Hierarchy Levels Assigned by Order of First Occurrence

`TitleClassifier` assigns level 0 to the first unique `TextStyle` encountered, level 1 to the second, etc. If a styled disclaimer appears before the first real heading, all levels shift. `PageHeaderClassifier` and `SupplementaryTextClassifier` catch some cases but edge cases remain (bold legal notices, centered company names, styled exhibit references).

**Impact:** Incorrect TOC nesting (G2), unreliable segment hierarchy (G1).

**Fix:** Two-pass with style scoring. Pass 1: collect all unique styles. Score by visual weight: `(bold * 3) + (uppercase * 2) + (centered * 2) + (underline * 1) - (italic * 1)`. Pass 2: assign levels by score rank.

#### M2. No Stable Element Identifier System

Elements have no `id`, `index`, or content-hash identifier. Identified only by Python object identity. `to_dict()` produces `html_hash` via xxhash on `HtmlTag` but it's not propagated as a stable element ID.

**Impact:** No segment addresses (G1), no TOC anchors (G2), no cross-period alignment (G5).

**Fix:** Post-tree-building step assigning hierarchical IDs. `TopSectionTitle` uses `.section_type.identifier`. `TitleElement` derives from parent + slugified title. Content elements use parent ID + type + index.

#### M3. Table Detection Has No Type Classification

`TableClassifier` produces a single `TableElement` type. No distinction between financial statements, footnotes, layout tables, exhibit lists, or schedules.

**Impact:** G3 requires classified inventory. G4 depends on table type for prose-stub logic.

**Fix:** `TableTypeClassifier` step. Heuristics: `$` markers and numeric columns = financial statement; smaller tables in footnote sections = footnote; single-column or text-heavy = layout.

#### M4. No Prose-Table Context Relationship Tracking

No step examines the relationship between a `TextElement` and adjacent `TableElement`. `SupplementaryTextClassifier` catches only a few specific patterns.

**Impact:** G4 cannot distinguish substantive prose from stub references.

**Fix:** `TableContextClassifier` step. Classify preceding text as stub-reference, substantive-context, or standalone.

#### M5. Tree Has No Section Boundary or Position Data

`TreeNode` has no start/end index, character offset, or document-position information.

**Impact:** G2's Intersection Observer needs scroll-to-section mapping. Without positional data the frontend must re-walk the DOM.

**Fix:** Track `start_index`, `end_index`, `char_offset` during tree construction. Expose `tree.get_section_map()`.

#### M6. `_find_parent_node` Destructively Pops the Stack

The `while stack` loop in `TreeBuilder._find_parent_node()` pops elements that don't match as parents. If element N can't find a parent, it destroys context that element N+1 might need.

**Impact:** After standalone tables or images, accumulated title context is lost. Subsequent elements become root nodes. Produces broken trees for G2 and incorrect addresses for G1.

**Fix:** Non-destructive backward search. Only trim the stack after finding a match or determining root status.

### Minor Flaws

| ID | Flaw | Location | Impact |
|----|------|----------|--------|
| m1 | Missing f-string in `TableElement.get_summary()` — returns literal `"{len(self.text)}"` instead of count | `table_element.py:23` | Bug |
| m2 | Dead code: module-level docstrings with "ChatGPT improved version" | `top_section_manager.py:347-379` | Clutter |
| m3 | All thresholds hard-coded, none exposed via `ParsingOptions` | Multiple files | Inflexibility |
| m4 | `match_part()` roman numeral map limited to I–IV | `top_section_manager.py` | Blocks G8 for some filing types |
| m5 | Page header/number detection requires 5+ occurrences; fails on short filings | `page_header_classifier.py`, `page_number_classifier.py` | Edge case for amendments |
| m6 | `render_()` has quadratic prefix growth for deeply nested trees | `render_.py:98` | Performance |
| m7 | Single-pass pipeline cannot reclassify elements once typed | Pipeline design | Table captions misclassified as titles |
| m8 | `TableOfContentsClassifier` only matches exact `{"page", "page no.", "page number"}` | `table_check_data_cell.py` | Missed TOC tables |
| m9 | `CompositeSemanticElement.unwrap_elements()` loses container context | `composite_semantic_element.py` | Affects G4 prose-table sibling detection |

---

## 8. Improvements

### Core (Do First)

These are blocking improvements required before meaningful downstream integration.

#### C1. Stable Hierarchical Element IDs

Add a post-tree-building step that assigns a deterministic `segment_id` to every element.

Format: `{section_identifier}:{title_slug}:{element_type}_{index}`
Examples: `part2item7:revenue_recognition:text_3`, `part1item1:financial_statements:table_1`

For `TopSectionTitle`, use `.section_type.identifier`. For `TitleElement`, slugify title text. For content elements, parent ID + type + index.

**Enables:** G1, G2, G5. This is the provenance anchor for the entire NLP pipeline.

#### C2. Fix Title Level Assignment

Convert `TitleClassifier` to two-pass (`_NUM_ITERATIONS = 2`). Pass 1: collect all unique `TextStyle` instances. Score by visual weight. Pass 2: assign levels by score rank.

Scoring: `(bold * 3) + (uppercase * 2) + (centered * 2) + (underline * 1) - (italic * 1)`.

**Enables:** G1, G2 — correct TOC hierarchy and segment nesting.

#### C3. Fix f-string Bug

Add the `f` prefix to the fallback return string in `TableElement.get_summary()`. Trivial.

#### C4. Section Boundary Data on Tree Nodes

Track `start_index` and `end_index` (position in flat element list) on each `TreeNode` during `TreeBuilder.build()`. Compute cumulative character offsets.

Expose `SemanticTree.get_section_boundaries()` → `list[(segment_id, start_idx, end_idx, char_start, char_end)]`.

**Enables:** G2 — Intersection Observer scroll-to-section mapping, progress-within-section display.

#### C5. TOC Data Structure Generation

Add `SemanticTree.to_toc()` method producing a serializable TOC.

Each entry: `segment_id`, `title`, `level`, `element_type`, `parent_id`, `child_count`, `has_tables`, `content_length`.

**Enables:** G2 — the floating pill UI's expandable TOC list needs exactly this data.

#### C6. Non-Destructive Stack in TreeBuilder

Replace the destructive `stack.pop()` loop in `_find_parent_node()` with a backward index scan. Only trim after finding a match or determining root status.

**Enables:** G1, G2 — fewer orphaned elements, more robust tree building.

#### C7. HTML Pre-Processing

Add `HtmlNormalizer` before `HtmlTagParser`: collapse `&nbsp;`, strip empty wrappers, normalize `<br/>` sequences, strip zero-width characters.

**Enables:** All goals — cleaner input improves all downstream classification accuracy.

#### C8. 8-K Filing Type Support

Add `FilingSectionsIn8K` (Items 1.01–9.01), `TopSectionManagerFor8K` (two-decimal item format), `Edgar8KParser`.

**Enables:** G8 — highest-signal filing type after 10-K/10-Q.

#### C9. Sentence Boundary Detection

Integrate spaCy (or pySBD as lighter alternative) with SEC-specific abbreviation rules. Produce `SentenceElement` objects as children of `TextElement`, each inheriting the parent's `segment_id` with `:s{index}` suffix.

**Enables:** G6 — sentence-level granularity for the NLP pipeline.

#### C10. Expand Test Suite & Accuracy Benchmarks

- Build a corpus of known-tricky filings (Berkshire Hathaway, Tesla, SPACs, bank holding companies)
- Manually annotate expected section boundaries for accuracy scoring
- Add cross-period consistency tests (same company across 3–4 years — structural diffs are either real changes or parser errors)
- Sentence-level accuracy tests for SEC-specific edge cases (abbreviations, note references, legal citations)
- Snapshot tests for regression detection

**Enables:** Quantitative accuracy tracking, confidence in parser output quality.

### Good to Have (Do Soon)

These improve quality and enable secondary goals but don't block initial integration.

#### G2-1. Table Type Classification

Add `TableTypeClassifier` step. Classify each `TableElement` as: `FINANCIAL_STATEMENT`, `FOOTNOTE`, `LAYOUT`, `TOC`, `SCHEDULE`, `OTHER`.

Heuristics: `$` markers + numeric columns → financial; smaller tables in footnote sections → footnote; single-column or text-heavy → layout.

**Enables:** G3.

#### G2-2. Table-Prose Context Classifier

Add `TableContextClassifier` step. For each `TableElement`, classify preceding text as:
- **Stub:** length < 120 chars AND matches "following table", "table below", "as follows", etc.
- **Substantive:** preceding text > 120 chars with analytical content
- **Standalone:** no preceding text, or preceding element is another table/title

**Enables:** G4.

#### G2-3. Expand SupplementaryTextClassifier

Broaden patterns: "Refer to [Note/table/section]...", "The following [table/chart]...", single-sentence paragraphs ending with colons, parenthetical references like "(see table X)".

**Enables:** G4.

#### G2-4. Diff-Ready Serialization

Add `SemanticTree.to_diff_text()` — one line per element: `{segment_id}\t{element_type}\t{normalized_text}`. Normalize: collapse whitespace, strip page artifacts, normalize quotes/dashes. Tables use `table_to_markdown()` output.

**Enables:** G5.

#### G2-5. Cross-Reference Detection

Regex-based detector for "see Note N", "as described in Item N", "refer to Part N" patterns. Produce link targets using `segment_id` of the referenced section.

**Enables:** G7.

#### G2-6. Footnote Detection

`FootnoteClassifier` step recognizing "Note N" / "NOTE N" patterns within financial statement sections. Produce `FootnoteElement` with `.note_number`. Improves TOC and provides high-signal NLP content.

**Enables:** G2, G6.

#### G2-7. Make Thresholds Configurable

Expand `ParsingOptions` to expose all hardcoded thresholds (style %, bold weight, page header occurrences, table row minimum). Pass through pipeline so each step reads from config.

**Enables:** Tuning for different filer styles without modifying internals.

#### G2-8. Rendering Hint Metadata

Expose on each element: `is_scrollable_table` (row count > threshold), text style as rendering directive (not just classification signal), table dimensions. Allow the reader to consume structural hints directly.

**Enables:** G9.

### To Consider (Evaluate Later)

These are worth investigating but may not justify the effort, or may be better solved outside the parser.

#### T1. Structural Boilerplate Hash Table

Ship a pre-built hash table of known boilerplate sentences (built from a large corpus). Parser looks up each normalized sentence and flags matches. Cheap, deterministic, high-accuracy.

**Trade-off:** Requires corpus construction and maintenance. May be better as a downstream data asset than a parser feature. Alternatively, the parser provides the normalized sentences and a separate boilerplate service does the lookup.

#### T2. DEF 14A Filing Support

Complex structure without rigid Part/Item format. Requires new section detection heuristics (compensation tables, proposal numbering, governance sections). High value but high effort.

#### T3. S-1/S-3 Filing Support

Similar to 10-K with additional sections. Moderate effort. Lower priority than 8-K and DEF 14A.

#### T4. Exhibit Boundary Detection

`ExhibitClassifier` step detecting "EXHIBIT X.X" boundaries. Classify as material vs. boilerplate by exhibit number convention (99.1 = material, 31.x/32.x = boilerplate certifications).

#### T5. Improve TableOfContentsClassifier

Case-insensitive matching, support for "Pg.", "PAGE", whitespace tolerance. Second heuristic: tables with 5+ rows where one column has section-title text and another has numbers → likely TOC.

#### T6. Parsed Output Caching

Content-hash-based disk cache for `SemanticTree`. Keyed by `hash(html_content + pipeline_config_hash)`. Avoids re-parsing during dev iteration.

#### T7. Clean Up Dead Code

Remove module-level algorithm descriptions at end of `top_section_manager.py`. Low priority but trivial.

#### T8. Table Caption vs. Title Disambiguation

Address m7: `TitleClassifier` promotes `HighlightedTextElement` to `TitleElement` even when the styled text is a table caption. Add a post-classification check: if a `TitleElement` immediately precedes a `TableElement` and is short, reclassify as `TableCaptionElement`.

#### T9. pySBD vs. spaCy Evaluation

Before committing to spaCy for sentence segmentation, prototype both approaches against a set of SEC-specific test cases. pySBD is lighter (pure Python, no model download) and may be sufficient for the rule-based abbreviation handling we need. spaCy brings more power (NER, dependency parsing) that could be useful for cross-reference detection but adds ~100MB of model weight.

---

## Appendix A: Improvement Summary Matrix

| ID | Improvement | Category | Effort | Primary Goals |
|----|------------|----------|--------|---------------|
| C1 | Stable hierarchical element IDs | Core | Medium | G1, G2, G5 |
| C2 | Fix title level assignment scoring | Core | Medium | G1, G2 |
| C3 | Fix f-string bug | Core | Trivial | Bug fix |
| C4 | Section boundary data on tree nodes | Core | Medium | G2 |
| C5 | TOC data structure generation | Core | Medium | G2 |
| C6 | Non-destructive tree builder stack | Core | Low | G1, G2 |
| C7 | HTML pre-processing | Core | Medium | All |
| C8 | 8-K filing type support | Core | Medium | G8 |
| C9 | Sentence boundary detection | Core | Medium | G6 |
| C10 | Expanded test suite & accuracy benchmarks | Core | High | All |
| G2-1 | Table type classification | Good to Have | Medium | G3 |
| G2-2 | Table-prose context classifier | Good to Have | Medium | G4 |
| G2-3 | Expand supplementary text rules | Good to Have | Low | G4 |
| G2-4 | Diff-ready serialization | Good to Have | Medium | G5 |
| G2-5 | Cross-reference detection | Good to Have | Medium | G7 |
| G2-6 | Footnote detection | Good to Have | Medium | G2, G6 |
| G2-7 | Configurable thresholds | Good to Have | Low | All |
| G2-8 | Rendering hint metadata | Good to Have | Low | G9 |
| T1 | Structural boilerplate hash table | To Consider | High | G6 |
| T2 | DEF 14A filing support | To Consider | High | G8 |
| T3 | S-1/S-3 filing support | To Consider | Medium | G8 |
| T4 | Exhibit boundary detection | To Consider | Medium | G2, G9 |
| T5 | Improve TOC classifier | To Consider | Low | G2 |
| T6 | Parsed output caching | To Consider | Medium | Performance |
| T7 | Clean up dead code | To Consider | Trivial | Maintenance |
| T8 | Table caption disambiguation | To Consider | Low | G2, G3 |
| T9 | pySBD vs. spaCy evaluation | To Consider | Low | G6 |

---

## Appendix B: File Map

| Component | File |
|-----------|------|
| Public API | `sec_parser/__init__.py` |
| Parser entry point | `sec_parser/processing_engine/core.py` |
| HTML tag wrapper | `sec_parser/processing_engine/html_tag.py` |
| HTML tag parser | `sec_parser/processing_engine/html_tag_parser.py` |
| Parsing options | `sec_parser/processing_engine/types.py` |
| Processing step base | `sec_parser/processing_steps/abstract_classes/abstract_elementwise_processing_step.py` |
| Batch step base | `sec_parser/processing_steps/abstract_classes/abstract_element_batch_processing_step.py` |
| Element extractor | `sec_parser/processing_steps/individual_semantic_element_extractor/individual_semantic_element_extractor.py` |
| Table check | `sec_parser/processing_steps/individual_semantic_element_extractor/single_element_checks/table_check.py` |
| XBRL check | `sec_parser/processing_steps/individual_semantic_element_extractor/single_element_checks/xbrl_tag_check.py` |
| Image classifier | `sec_parser/processing_steps/image_classifier.py` |
| Empty classifier | `sec_parser/processing_steps/empty_element_classifier.py` |
| Table classifier | `sec_parser/processing_steps/table_classifier.py` |
| TOC classifier | `sec_parser/processing_steps/table_of_contents_classifier.py` |
| Section manager | `sec_parser/processing_steps/top_section_manager.py` |
| Intro classifier | `sec_parser/processing_steps/introductory_section_classifier.py` |
| Text classifier | `sec_parser/processing_steps/text_classifier.py` |
| Highlighted text | `sec_parser/processing_steps/highlighted_text_classifier.py` |
| Supplementary text | `sec_parser/processing_steps/supplementary_text_classifier.py` |
| Page header | `sec_parser/processing_steps/page_header_classifier.py` |
| Page number | `sec_parser/processing_steps/page_number_classifier.py` |
| Title classifier | `sec_parser/processing_steps/title_classifier.py` |
| Text merger | `sec_parser/processing_steps/text_element_merger.py` |
| Base element | `sec_parser/semantic_elements/abstract_semantic_element.py` |
| Element types | `sec_parser/semantic_elements/semantic_elements.py` |
| Highlighted element | `sec_parser/semantic_elements/highlighted_text_element.py` |
| Title element | `sec_parser/semantic_elements/title_element.py` |
| Top section title | `sec_parser/semantic_elements/top_section_title.py` |
| Top section marker | `sec_parser/semantic_elements/top_section_start_marker.py` |
| Section definitions | `sec_parser/semantic_elements/top_section_title_types.py` |
| Table element | `sec_parser/semantic_elements/table_element/table_element.py` |
| Table parser | `sec_parser/semantic_elements/table_element/table_parser.py` |
| Table to markdown | `sec_parser/utils/bs4_/table_to_markdown.py` |
| TOC check | `sec_parser/utils/bs4_/table_check_data_cell.py` |
| Table metrics | `sec_parser/utils/bs4_/approx_table_metrics.py` |
| Composite element | `sec_parser/semantic_elements/composite_semantic_element.py` |
| Tree builder | `sec_parser/semantic_tree/tree_builder.py` |
| Nesting rules | `sec_parser/semantic_tree/nesting_rules.py` |
| Semantic tree | `sec_parser/semantic_tree/semantic_tree.py` |
| Tree node | `sec_parser/semantic_tree/tree_node.py` |
| Render | `sec_parser/semantic_tree/render_.py` |
