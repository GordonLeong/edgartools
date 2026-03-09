
sec-parser donor analysis for scotch-parser (v0.1)
1) Repo map (high-level)
Core pipeline entrypoints
sec_parser.processing_engine.core.AbstractSemanticElementParser.parse and .parse_from_tags are the real runtime entrypoints. They parse HTML into HtmlTag wrappers, run an ordered processing pipeline, then optionally flatten composites. (No standalone CLI in this repo for production parsing.)
Filing-specific orchestrators are:
sec_parser.processing_engine.core.Edgar10KParser.get_default_steps
sec_parser.processing_engine.core.Edgar10QParser.get_default_steps
Tree construction is separate from extraction/classification:
sec_parser.semantic_tree.tree_builder.TreeBuilder.build
Uses rules in sec_parser.semantic_tree.nesting_rules.
Parsing logic location and data flow
Input parsing/wrapper:
sec_parser.processing_engine.html_tag_parser.HtmlTagParser.parse
sec_parser.processing_engine.html_tag.HtmlTag (wrapper + utility/cache layer).
Pipeline steps (structure heuristics live here):
sec_parser/processing_steps/*
Particularly: top_section_manager.py, individual_semantic_element_extractor/*, title_classifier.py, table_classifier.py, table_of_contents_classifier.py, text_element_merger.py, header/footer-ish classifiers.
Structure objects:
semantic elements in sec_parser/semantic_elements/*
top section definitions in top_section_title_types.py
table adapters in semantic_elements/table_element/*
Tree assembly:
semantic_tree/tree_builder.py + nesting_rules.py.
Tight coupling / output format coupling
Strongly coupled to custom class hierarchy (AbstractSemanticElement subclasses), mutable processing_log, and repeated in-place type conversion in pipeline passes.
Coupled to BeautifulSoup via HtmlTag helper methods and utility functions under utils/bs4_.
Table handling coupled to pandas (pd.read_html) and markdown rendering (tabulate through pandas).
Section ontology is hardcoded for 10-K/10-Q in top_section_title_types.py; this is useful donor logic but needs extraction into data-driven mapping in scotch-parser.
2) Heuristic inventory (function-by-function extraction plan)
H1. Top section candidate regex and part/item normalization
Function: sec_parser.processing_steps.top_section_manager.TopSectionManager.match_part / match_item
Path: sec_parser/processing_steps/top_section_manager.py:75-88
Purpose: Detect Part I/II/... and Item 1A/7/... from line-start text and normalize to IDs.
Inputs: raw element text + regex:
part\s+([iv]+)
item\s+(\d+[a-c]?)
Outputs: normalized part number ("1".."4") or item token ("1a", "7").
Determinism: deterministic regex matching on current text.
Robustness:
Handles Roman numerals I–IV only.
Misses e.g. PART ONE, ITEM 7A— with punctuation variants before token, and higher roman numerals.
Overlap vs edgartools: Partially.
Steal score: 4/5.
Extracted pass shape (score >=3):
Pass name: normalize_sec_item_markers
Pipeline slot: after base block extraction (edgartools base tree), before section-boundary resolution.
Minimal input: block text + source order index.
Output: optional {marker_type, part, item, confidence} on block metadata.
Tests:
Positive: "PART II - ITEM 7A." -> {part:2,item:'7a'}.
Negative: "This part of our strategy" -> no marker.
Risk notes: avoid eager start-of-line-only assumption when sanitizer changes whitespace.
H2. Two-pass top-section candidate collection
Function: TopSectionManager._process_element, _process_iteration_0, _process_iteration_1, _identify_candidate
Path: sec_parser/processing_steps/top_section_manager.py:112-142,160-189
Purpose: first pass collects candidate blocks that look like section markers; second pass upgrades selected candidates to TopSectionTitle.
Inputs: ordered semantic element stream, mutable manager state (_last_part, _candidates).
Outputs: candidate list then transformed section-title nodes.
Determinism: depends on traversal order and mutable state.
Robustness: strong for linear documents; weak if DOM order differs from visual order.
Overlap vs edgartools: Partially.
Steal score: 4/5.
Extracted pass shape:
Pass name: collect_and_promote_top_section_titles
Slot: after marker normalization, before tree nesting.
Input: ordered blocks with normalized marker metadata.
Output: section-title annotations + provenance (source_block_id).
Tests:
Positive: duplicated Item 1A in TOC/body should promote body candidate.
Negative: single stray item 3 in footnote should not start section.
Risk: multi-pass state must be explicit and pure (avoid hidden mutable object fields).
H3. Candidate selection with table-avoidance filter
Function: TopSectionManager._select_candidates
Path: sec_parser/processing_steps/top_section_manager.py:215-251
Purpose: for each section ID, picks first candidate; prefers candidates not containing <table>.
Inputs: grouped candidates by section type + contains_tag('table').
Outputs: one selected candidate per section ID.
Determinism: deterministic but order-sensitive.
Robustness:
Good for TOC-vs-body disambiguation when TOC is table-based.
Fails if true section heading is inside table layout.
Overlap vs edgartools: Not covered (likely).
Steal score: 5/5.
Extracted pass shape:
Pass name: resolve_duplicate_section_marker_candidates
Slot: after candidate collection.
Input: candidate list with contains_table, text density, anchor presence.
Output: selected candidate IDs + suppression reasons.
Tests:
Positive: same marker in TOC table and body paragraph -> body wins.
Negative: only table-based heading exists -> keep table candidate.
Risk: add backoff scoring; do not hard-fail on table presence.
H4. Monotonic section-order gate
Function: TopSectionManager._process_selected_candidates
Path: sec_parser/processing_steps/top_section_manager.py:266-281
Purpose: only promote a section candidate if its canonical order is greater than last accepted order.
Inputs: selected candidates + section_type.order + mutable _last_order_number.
Outputs: prevents regressions (e.g., repeated older item references).
Determinism: deterministic, order-sensitive.
Robustness: can drop valid repeated sections in amended filings; good for noisy repeats.
Overlap vs edgartools: Unknown/partial.
Steal score: 4/5.
Extracted pass shape:
Pass name: enforce_monotonic_item_progression
Slot: after candidate resolution.
Input: selected candidate sequence + canonical SEC order mapping.
Output: accepted/rejected flags with reason.
Tests:
Positive: item1,item1a,item2 all accepted.
Negative: later item1 reference after item7 rejected.
Risk: must allow explicit reset at new Part boundary.
H5. Top-section split trigger in nested mixed blocks
Function: TopSectionTitleCheck.contains_single_element
Path: sec_parser/processing_steps/individual_semantic_element_extractor/single_element_checks/top_section_title_check.py:22-32
Purpose: if descendants contain part/item markers, force block splitting into child elements.
Inputs: descendant text count match using callback + exclude_links=True.
Outputs: returns False to trigger split into composite.
Determinism: deterministic.
Robustness: link exclusion helps avoid TOC hyperlinks; still regex-fragile.
Overlap vs edgartools: Partially.
Steal score: 4/5.
Extracted pass shape:
Pass name: split_mixed_blocks_on_item_markers
Slot: early block segmentation enrichment.
Input: DOM subtree + visible text nodes.
Output: finer-grained blocks around marker-containing descendants.
Tests:
Positive: paragraph containing two item headings splits.
Negative: list of links in TOC should not explode into noise blocks.
Risk: over-segmentation.
H6. Table/text mixed-node split heuristic
Function: TableCheck.contains_single_element
Path: sec_parser/processing_steps/individual_semantic_element_extractor/single_element_checks/table_check.py:15-38
Purpose: split nodes when multiple tables or table+outside-text co-exist.
Inputs: descendant table count, text outside table tags.
Outputs: False to force composite split.
Determinism: deterministic.
Robustness: useful for table wrappers; weak for legitimate caption+table patterns.
Overlap vs edgartools: Partially.
Steal score: 5/5.
Extracted pass shape:
Pass name: split_table_and_non_table_content
Slot: pre-table-classification segmentation pass.
Input: subtree node.
Output: separate table block(s) and neighbor text blocks with shared parent provenance.
Tests:
Positive: <div>caption<table>...</table></div> -> caption + table blocks.
Negative: pure single <table> remains unsplit.
Risk: keep caption association metadata.
H7. XBRL tag forced split
Function: XbrlTagCheck.contains_single_element
Path: sec_parser/processing_steps/individual_semantic_element_extractor/single_element_checks/xbrl_tag_check.py:15-24
Purpose: split ix:* containers that often bundle many semantic units.
Inputs: tag name prefix check.
Outputs: False split decision.
Determinism: deterministic.
Robustness: good default for inline XBRL filings.
Overlap vs edgartools: Unknown.
Steal score: 4/5.
Extracted pass shape:
Pass name: split_inline_xbrl_wrappers
Slot: earliest DOM-to-block segmentation.
Input: DOM node tag name and children.
Output: child blocks extracted with stable offsets.
Tests:
Positive: ix:nonnumeric with two spans -> two blocks eligible for merge later.
Negative: non-ix wrapper unchanged.
Risk: issuer custom namespaces (not just ix:).
H8. Adjacent text block merge
Function: TextElementMerger._process_elements / _merge
Path: sec_parser/processing_steps/text_element_merger.py:39-68,70-93
Purpose: merge contiguous text elements separated only by irrelevant elements.
Inputs: ordered elements + types (TextElement, IrrelevantElement).
Outputs: merged text block with wrapped synthetic parent tag.
Determinism: deterministic and order-dependent.
Robustness: fixes XBRL span fragmentation; risks accidental paragraph over-merge.
Overlap vs edgartools: Partially.
Steal score: 5/5.
Extracted pass shape:
Pass name: merge_fragmented_text_runs
Slot: after segmentation and trivial type classification, before sentence splitting.
Input: linear block list with adjacency and block roles.
Output: merged block IDs + lineage map of source block IDs.
Tests:
Positive: split token "co" + "nsisted" merges into one sentence block.
Negative: two distinct paragraphs with intervening non-irrelevant block stay separate.
Risk: preserve provenance fan-in for card pipeline.
H9. Highlight/style-based title level induction
Function: HighlightedTextClassifier._process_element + TitleClassifier._process_element
Path: sec_parser/processing_steps/highlighted_text_classifier.py:38-51, sec_parser/processing_steps/title_classifier.py:47-71
Purpose: detect emphasized text styles and assign heading levels by first-seen style order.
Inputs: per-node style metrics + mutable ordered unique style list.
Outputs: HighlightedTextElement then TitleElement(level=k).
Determinism: deterministic but corpus-order dependent.
Robustness: works on consistent issuer templates; unstable across issuers.
Overlap vs edgartools: Partially.
Steal score: 3/5.
Extracted pass shape:
Pass name: infer_heading_candidates_from_style
Slot: after base headings from semantic cues, as fallback enrichment.
Input: block text + normalized computed style signature.
Output: heading candidate score + inferred depth bucket.
Tests:
Positive: repeated bold uppercase style promoted to heading.
Negative: bold inline emphasis in paragraph not promoted.
Risk: do not hard-assign tree depth from style order alone.
H10. Table classification via approximate metrics
Function: TableClassifier._process_element and get_approx_table_metrics
Path: sec_parser/processing_steps/table_classifier.py:37-62, sec_parser/utils/bs4_/approx_table_metrics.py:20-32
Purpose: classify as table when <table> exists and row count > threshold.
Inputs: table presence + metric extraction (rows, numbers).
Outputs: TableElement conversion.
Determinism: deterministic with exception-based fallback.
Robustness: cheap and fast; brittle with nested layout tables and malformed rows.
Overlap vs edgartools: Covered/partial.
Steal score: 3/5.
Extracted pass shape:
Pass name: qualify_table_blocks
Slot: after table/non-table split.
Input: table DOM blocks.
Output: table classification + quality metrics.
Tests:
Positive: financial statement table with multiple rows recognized.
Negative: one-row layout table rejected or low-confidence.
Risk: avoid silent exception swallowing; emit failure counters.
H11. TOC detection via “page” table-cell heuristic
Function: TableOfContentsClassifier._process_element + check_table_contains_text_page
Path: sec_parser/processing_steps/table_of_contents_classifier.py:38-51, sec_parser/utils/bs4_/table_check_data_cell.py:6-29
Purpose: mark tables as TOC when any cell equals page/page no./page number.
Inputs: single-table extraction + td text equality set.
Outputs: TableOfContentsElement.
Determinism: deterministic.
Robustness: precision okay for standard TOCs; misses variants (pg, localized labels), false positives in random schedules.
Overlap vs edgartools: Partially.
Steal score: 4/5.
Extracted pass shape:
Pass name: detect_table_of_contents_tables
Slot: after table qualification.
Input: parsed table text matrix + nearby heading context.
Output: TOC flag + confidence.
Tests:
Positive: classic TOC table with page column.
Negative: compensation table containing word "page" once not TOC.
Risk: include contextual guardrails (position near beginning).
H12. Introductory pre-part labeling
Function: IntroductorySectionElementClassifier._process_element
Path: sec_parser/processing_steps/introductory_section_classifier.py:43-69
Purpose: mark everything before part1 top marker as introductory section.
Inputs: presence and first position of TopSectionTitle(identifier='part1').
Outputs: IntroductorySectionElement conversions.
Determinism: deterministic, two-pass stateful.
Robustness: good for filings with standard part markers; fails when part labels absent.
Overlap vs edgartools: Unknown.
Steal score: 3/5.
Extracted pass shape:
Pass name: label_preface_region
Slot: after top-section boundary detection.
Input: block sequence with top-section indices.
Output: preface region tag for blocks.
Tests:
Positive: cover page + TOC before part1 tagged preface.
Negative: no part1 marker => no broad preface relabel.
Risk: if marker missed, pass should no-op safely.
H13. Repeated header/footer detection by frequency
Function: PageHeaderClassifier._find_page_header_candidates, _get_most_common_candidates, _classify_elements; and PageNumberClassifier equivalents
Path: sec_parser/processing_steps/page_header_classifier.py:64-101, sec_parser/processing_steps/page_number_classifier.py:69-119
Purpose: classify repeated short strings/digit patterns as page headers/numbers.
Inputs: text length thresholds + corpus frequency + style for header.
Outputs: header/page number element conversions.
Determinism: deterministic across fixed ordering.
Robustness: useful for repeated artifacts; may suppress meaningful repeated headings.
Overlap vs edgartools: Unknown.
Steal score: 3/5.
Extracted pass shape:
Pass name: suppress_repeating_page_artifacts
Slot: before final tree assembly and sentence export.
Input: normalized text blocks and page/position signals.
Output: artifact tags + exclusion flags for downstream card creation.
Tests:
Positive: repeated "Company Name | 2023" across pages classified header.
Negative: repeated legal phrase in body not removed due positional mismatch.
Risk: needs page segmentation metadata (not present in raw DOM order alone).
H14. Supplementary parenthetical/notes classifier
Function: SupplementaryTextClassifier._process_element
Path: sec_parser/processing_steps/supplementary_text_classifier.py:44-88
Purpose: detect parenthetical or italicized note-like fragments (e.g., accompanying notes).
Inputs: text shape + italic style + phrase rules.
Outputs: SupplementaryText conversion.
Determinism: deterministic.
Robustness: narrow, can help table note separation; English phrase-dependent.
Overlap vs edgartools: Unknown.
Steal score: 2/5.
Plan: park for later; rewrite as feature flags, not hard type conversion.
H15. Composite extraction by child splitting
Function: IndividualSemanticElementExtractor._create_composite_element, _contains_single_element
Path: sec_parser/processing_steps/individual_semantic_element_extractor/individual_semantic_element_extractor.py:50-69,82-94
Purpose: when a node likely contains multiple semantic units, split into child elements and recursively process.
Inputs: has_tag_children + check chain output.
Outputs: CompositeSemanticElement(inner_elements=[...]).
Determinism: deterministic recursion over child order.
Robustness: strong foundational split mechanism.
Overlap vs edgartools: Partially.
Steal score: 5/5.
Extracted pass shape:
Pass name: recursive_dom_block_splitter
Slot: first enrichment pass after sanitizer/stamper and base DOM parse.
Input: DOM node + split ruleset.
Output: block graph with parent-child provenance edges.
Tests:
Positive: mixed node splits into heading/text/table children.
Negative: unary text node remains atomic.
Risk: recursion depth and runaway splits; add max-depth guard.
H16. Tree nesting rules and parent stack algorithm
Function: TreeBuilder.build, _find_parent_node, _should_nest_under
Path: sec_parser/semantic_tree/tree_builder.py:65-119
Purpose: single-pass stack algorithm to nest linear elements into a semantic tree by rule evaluation.
Inputs: ordered elements + nesting rules.
Outputs: SemanticTree.
Determinism: deterministic with ordered input.
Robustness: good baseline; heavily dependent on rule quality.
Overlap vs edgartools: Partially.
Steal score: 4/5.
Extracted pass shape:
Pass name: build_semantic_tree_from_scored_boundaries
Slot: final structural assembly after enrichment tags are settled.
Input: enriched block sequence with heading/section markers.
Output: semantic tree + stable node ids.
Tests:
Positive: heading/subheading/paragraph nests correctly.
Negative: repeated same-level heading should pop stack, not deep-nest.
Risk: rule conflicts; require deterministic priority ordering.
H17. Canonical 10-K/10-Q item ontology table
Object: FilingSectionsIn10K, FilingSectionsIn10Q
Path: sec_parser/semantic_elements/top_section_title_types.py (section tuples)
Purpose: hardcoded identifier→title/order/level map for section normalization.
Inputs: matched marker IDs.
Outputs: canonical order/level used in progression gate.
Determinism: deterministic static mapping.
Robustness: high for standard filings; brittle to form-specific variation.
Overlap vs edgartools: Partially.
Steal score: 5/5.
Extracted pass shape:
Pass name: canonical_sec_section_registry
Slot: shared lookup used by boundary passes.
Input: filing form type + normalized marker token.
Output: canonical section metadata.
Tests:
Positive: 10-K part2item7a resolves with correct order.
Negative: 10-Q-only marker on 10-K returns unknown.
Risk: versioning when SEC item schema changes.
3) Secondary capabilities (non-core)
Steal as-is
sec_parser/utils/bs4_/get_single_table.py:
tiny, clear invariant checker (0/1 table enforcement) with explicit errors.
Small predicate helpers (contains_tag, count_tags, has_text_outside_tags) conceptually useful; re-implement against your DOM abstraction if APIs differ.
Rewrite cheaply
table_to_markdown.py and table_element/table_parser.py:
ideas are good (colspan expansion, duplicate/blank column cleanup) but pandas-coupled and mutation-heavy.
rewrite as deterministic table IR normalization pass (no markdown first).
HighlightedTextClassifier / TextStyle usage:
keep idea of style signature; rewrite scoring model to avoid first-seen-style level lock-in.
Page header/number classifiers:
keep frequency concept, but add page-position signal and confidence thresholds tied to false positive budget.
Do not steal
Dev dashboard app under dev_utils/dashboard_app/*: not part of semantic tree quality.
Streamlit compatibility hacks inside HtmlTag.get_source_code(enable_compatibility=True); irrelevant to core parser output substrate.
Monolithic mutable processing-log behavior as control signal; keep provenance but do not carry this architecture.
Notes on requested categories
HTML cleaning/sanitization: mostly skip (you already have sanitizer/stamper). No clearly superior sanitizer in donor.
Normalization/tokenization: only selective phrase heuristics worth lifting.
Table serialization/formatting: keep heuristics, rewrite implementation.
Issuer-specific patterns: very limited in this repo; mostly generic form-item assumptions.
Debug tooling: tests/fixtures are useful as donor corpus, not runtime code.
Performance/caching: HtmlTag caches many computed values; keep pattern idea, but not class design wholesale.
4) Architecture extraction plan (summary)
Top 10 to port first (ranked)
resolve_duplicate_section_marker_candidates (from H3)
recursive_dom_block_splitter (H15)
split_table_and_non_table_content (H6)
merge_fragmented_text_runs (H8)
canonical_sec_section_registry (H17)
collect_and_promote_top_section_titles (H2)
normalize_sec_item_markers (H1)
enforce_monotonic_item_progression (H4)
detect_table_of_contents_tables (H11)
build_semantic_tree_from_scored_boundaries (H16)
Next 10 (“later”)
split_inline_xbrl_wrappers (H7)
split_mixed_blocks_on_item_markers (H5)
qualify_table_blocks (H10)
infer_heading_candidates_from_style (H9)
label_preface_region (H12)
suppress_repeating_page_artifacts (H13)
supplementary-note tagging (H14)
table colspan unmerge idea from table_to_markdown
duplicate blank-column pruning idea from table_parser
selected bs4 helper predicates reimplemented for your DOM API
Explicit do-not-steal list
dev_utils/**
mutable processing_log-driven architecture as control plane
output class hierarchy shape (AbstractSemanticElement inheritance tree)
direct pandas-based markdown conversion as primary table pipeline
Proposed folder layout in packages/scotch-parser/
packages/scotch-parser/src/scotch_parser/enrichment/
passes/
splitter_recursive.py
splitter_table_mixed.py
splitter_xbrl.py
markers_normalize.py
markers_collect_sections.py
sections_resolve_duplicates.py
sections_monotonic_order.py
headings_style_fallback.py
tables_classify.py
tables_detect_toc.py
text_merge_fragments.py
artifacts_page_repetition.py
registry/
sec_items_10k_10q.py
models/
block_features.py
section_annotations.py
table_features.py
packages/scotch-parser/tests/enrichment/
pass-level focused fixtures (small HTML snippets)
filing-level golden mini-corpus
Minimal quality harness plan (keep/drop gate)
Compute these metrics for each pass-on/pass-off A/B run over fixed filing set:

Section boundary F1 against manually curated item boundaries.
Heading precision/recall for promoted heading nodes.
Block fragmentation index:
mean chars per block
% singleton-token blocks
Table extraction quality:
true table recall
false table rate (layout tables)
TOC false-positive rate.
Provenance completeness:
% output blocks with stable source anchor/id lineage.
Determinism check:
hash of semantic tree + sidecar must be identical across 3 runs.
Downstream utility proxy:
% card rows with section_id + block_id + sentence span all non-null.
Acceptance rule (simple): keep a heuristic only if it improves at least one target metric without regressing determinism or provenance completeness.
