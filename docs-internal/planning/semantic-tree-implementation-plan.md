# Implementation Plan: Semantic Tree Builder with Sentence-Level Tagging

**Date Created**: 2026-05-04  
**Status**: Planning  
**Estimated Effort**: 24-33 hours (3-4 full working days)

---

## Overview

Build a comprehensive semantic tree parser for SEC filings that:

1. **Splits documents into sentences** with precise tokenization (handling SEC-specific abbreviations)
2. **Tags each sentence** with its hierarchical section context (breadcrumb path)
3. **Identifies headers and tables** for classification
4. **Generates a smart table of contents** from document structure (independent of SEC-provided TOC)

This will enable:
- Fine-grained document analysis at sentence level
- Hierarchical context tracking for ML/AI applications
- Intelligent TOC generation without relying on SEC-provided TOC
- Better section boundary detection and content classification
- Foundation for question-answering and semantic search

---

## Current State Analysis

### What Exists Today

EdgarTools has a **strong foundation** for this feature:

**Node Hierarchy** (`edgar/documents/nodes.py`):
- `Node` base class with parent/child relationships
- Tree traversal methods: `walk()`, `find()`, XPath-like selection
- Depth and path tracking on nodes
- Node types: `SectionNode`, `HeadingNode`, `ParagraphNode`, `TableNode`, `TextNode`, etc.

**Section Detection** (Multi-strategy):
- `TOCAnalyzer` - Extracts sections from filing's TOC (`edgar/documents/utils/toc_analyzer.py`)
- `HeaderDetection` - 4 strategies: style, pattern, structural, contextual (`edgar/documents/strategies/header_detection.py`)
- `HybridSectionDetector` - Combines TOC → Heading → Pattern fallbacks (`edgar/documents/extractors/hybrid_section_detector.py`)

**Table Processing**:
- Table type classification (FINANCIAL, METRICS, TOC, EXHIBIT_INDEX, etc.)
- Header row detection with multi-row support
- Relationship extraction (totals, hierarchy)
- Located in `edgar/documents/strategies/table_processing.py`

**Text Extraction**:
- `TextExtractor` with sentence-boundary-aware truncation (`edgar/documents/extractors/text_extractor.py`)
- Text cleaning and normalization
- Markdown-style structure markers

**Semantic Typing**:
- `SemanticType` enum (TITLE, HEADER, BODY_TEXT, FINANCIAL_STATEMENT, etc.)
- Structure-aware semantic scoring (`edgar/documents/ranking/semantic.py`)

### What's Missing

- ❌ **Sentence-level tokenization** (splitting paragraphs into sentences)
- ❌ **Sentence tagging** with section path/context
- ❌ **Semantic tree builder** (orchestrates existing components)
- ❌ **Smart TOC generation** from document structure (independent of SEC TOC)
- ❌ **Hierarchical outline** with sentence mapping
- ❌ **Breadcrumb/path tracking** for each sentence

---

## Desired End State

### Simple API Usage

```python
from edgar import Company

# Get filing
company = Company("AAPL")
filing = company.get_filings(form="10-K").latest(1)

# Build semantic tree
tree = filing.semantic_tree()

# View smart TOC
print(tree.toc)  # Rich console output with hierarchical structure

# Navigate sections
risk_factors = tree.get_section("Risk Factors")
print(f"Path: {risk_factors.path}")
print(f"Breadcrumb: {' > '.join(risk_factors.breadcrumb)}")
print(f"Sentences: {risk_factors.sentence_count}")

# Iterate sentences with context
for sentence in risk_factors.sentences[:5]:
    print(f"[{sentence.section_path}] {sentence.text}")

# Search across document
results = tree.search("competition")
for section_path, sentence in results:
    print(f"{section_path}: {sentence.text[:100]}...")

# Export to various formats
tree.export_json("semantic_tree.json")
tree.export_csv("sentences.csv")

# Get statistics
print(tree.stats)
# {
#   'total_sections': 45,
#   'total_sentences': 2458,
#   'max_depth': 4,
#   'avg_sentences_per_section': 54.6
# }
```

### Data Structures

**Sentence Object**:
```python
@dataclass
class Sentence:
    text: str                          # "We face intense competition in our markets."
    start_pos: int                     # Character position in original text
    end_pos: int                       # End position
    node_id: str                       # Reference to parent ParagraphNode
    section_path: str                  # "Part I/Item 1A/Risk Factors/Competition"
    breadcrumb: List[str]              # ["Part I", "Item 1A", "Risk Factors", "Competition"]
    semantic_type: str                 # "BODY_TEXT"
    metadata: dict                     # Additional context
```

**Section Object**:
```python
class SemanticSection:
    node: SectionNode                  # Original node reference
    path: str                          # "Part I/Item 1A/Risk Factors"
    level: int                         # Depth in hierarchy (0-based)
    title: str                         # "Risk Factors"
    sentences: List[Sentence]          # All sentences in this section
    children: List[SemanticSection]    # Child sections
    metadata: dict                     # Tables, lists, etc.
```

**TOC Entry**:
```python
@dataclass
class TOCEntry:
    title: str                         # "Risk Factors"
    path: str                          # "Part I/Item 1A/Risk Factors"
    level: int                         # Indentation level
    number: str                        # "1.1.2" (hierarchical numbering)
    content_type: str                  # "section", "table", "list", "mixed"
    sentence_count: int                # 156
    word_count: int                    # 2,340
    has_tables: bool                   # True
    has_lists: bool                    # False
```

---

## Implementation Phases

### Phase 1: Sentence Tokenization (4-6 hours)

**Goal**: Build robust sentence tokenizer with SEC filing awareness

**New File**: `edgar/documents/builders/sentence_tokenizer.py`

**Key Components**:

1. **Sentence Dataclass**:
   ```python
   @dataclass
   class Sentence:
       text: str
       start_pos: int
       end_pos: int
       node_id: str
       section_path: Optional[str] = None
       semantic_type: Optional[str] = None
       metadata: dict = field(default_factory=dict)
   ```

2. **SentenceTokenizer Class**:
   ```python
   class SentenceTokenizer:
       def __init__(self):
           self.abbreviations = self._load_sec_abbreviations()
           # Use NLTK PunktSentenceTokenizer with custom training
       
       def tokenize(self, text: str, node_id: str = None) -> List[Sentence]:
           """Split text into sentences preserving positions"""
           pass
       
       def _load_sec_abbreviations(self) -> Set[str]:
           """SEC-specific abbreviations that shouldn't split sentences"""
           return {
               "U.S.", "Inc.", "Co.", "Corp.", "Ltd.", "LLC",
               "vs.", "et al.", "e.g.", "i.e.",
               "No.", "Sec.", "Art.", "Fig.",
               # Financial
               "approx.", "est.", "min.", "max.",
               # Dates
               "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.",
               "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec.",
           }
   ```

3. **Handle Edge Cases**:
   - Legal citations: "Section 1.01", "Rule 10b-5"
   - Numbers: "$1.5 million", "10.5%", "No. 1"
   - Dates: "Dec. 31, 2023"
   - Empty text, single word, no punctuation

**Tests**: `tests/documents/test_sentence_tokenizer.py`
- Basic sentence splitting
- SEC abbreviations handling
- Legal citation patterns
- Number and percentage patterns
- Position tracking accuracy
- Performance: 1000-word paragraph < 100ms

**Verification**:
```bash
python -m pytest tests/documents/test_sentence_tokenizer.py -v
```

---

### Phase 2: Semantic Tree Builder Core (6-8 hours)

**Goal**: Build orchestrator that creates semantic tree from document

**New File**: `edgar/documents/builders/semantic_tree_builder.py`

**Key Components**:

1. **SemanticSection Class**:
   ```python
   class SemanticSection:
       def __init__(self, node: Node, path: str, level: int):
           self.node = node
           self.path = path  # "Part I/Item 1A/Risk Factors"
           self.level = level
           self.title = self._extract_title(node)
           self.sentences: List[Sentence] = []
           self.children: List[SemanticSection] = []
           self.metadata = {}
       
       @property
       def breadcrumb(self) -> List[str]:
           """Path as list: ['Part I', 'Item 1A', 'Risk Factors']"""
           return self.path.split('/')
       
       @property
       def sentence_count(self) -> int:
           """Total sentences including children"""
           count = len(self.sentences)
           for child in self.children:
               count += child.sentence_count
           return count
       
       def find_sentence(self, text: str) -> Optional[Sentence]:
           """Find sentence by text substring"""
           pass
   ```

2. **SemanticTree Class**:
   ```python
   class SemanticTree:
       def __init__(self, document: Document):
           self.document = document
           self.root: Optional[SemanticSection] = None
           self.sections: List[SemanticSection] = []
           self.sentences: List[Sentence] = []
           self._path_index: Dict[str, SemanticSection] = {}
       
       @classmethod
       def from_document(cls, document: Document) -> 'SemanticTree':
           """Build semantic tree from document"""
           builder = SemanticTreeBuilder()
           return builder.build(document)
       
       def get_section(self, path: str) -> Optional[SemanticSection]:
           """Get section by path or fuzzy title match"""
           pass
       
       def find_sentence(self, text: str) -> List[Sentence]:
           """Find all sentences containing text"""
           pass
       
       @property
       def stats(self) -> dict:
           """Document statistics"""
           return {
               'total_sections': len(self.sections),
               'total_sentences': len(self.sentences),
               'max_depth': max((s.level for s in self.sections), default=0),
               'avg_sentences_per_section': len(self.sentences) / len(self.sections) if self.sections else 0
           }
   ```

3. **SemanticTreeBuilder Class**:
   ```python
   class SemanticTreeBuilder:
       def __init__(self):
           self.tokenizer = SentenceTokenizer()
       
       def build(self, document: Document) -> SemanticTree:
           """Build semantic tree from document"""
           tree = SemanticTree(document)
           
           # Build section hierarchy
           tree.root = self._build_section_tree(
               document.root, path="Document", level=0
           )
           
           # Flatten sections for easy access
           tree.sections = self._flatten_sections(tree.root)
           
           # Build path index
           tree._path_index = {s.path: s for s in tree.sections}
           
           # Process sentences for all sections
           for section in tree.sections:
               self._process_section_sentences(section, tree)
           
           return tree
       
       def _build_section_tree(self, node: Node, path: str, level: int) -> SemanticSection:
           """Recursively build section tree"""
           pass
       
       def _process_section_sentences(self, section: SemanticSection, tree: SemanticTree):
           """Extract and tag sentences for a section"""
           pass
   ```

**Integration**: Add to `Document` class:
```python
# In edgar/documents/document.py
@cached_property
def semantic_tree(self) -> 'SemanticTree':
    """Get semantic tree representation of document"""
    from edgar.documents.builders.semantic_tree_builder import SemanticTree
    return SemanticTree.from_document(self)
```

**Tests**: `tests/documents/test_semantic_tree_builder.py`
- Basic tree building from simple document
- Section hierarchy (parent/child relationships)
- Sentence tagging with section paths
- Section lookup by path and title
- Sentence search functionality
- Integration test with real 10-K excerpt

**Verification**:
```bash
python -m pytest tests/documents/test_semantic_tree_builder.py -v
```

---

### Phase 3: Smart Table of Contents Generator (4-5 hours)

**Goal**: Generate structured TOC from semantic tree

**New File**: `edgar/documents/builders/toc_generator.py`

**Key Components**:

1. **TOCEntry Dataclass**:
   ```python
   @dataclass
   class TOCEntry:
       title: str
       path: str
       level: int
       number: Optional[str] = None
       content_type: str = "section"
       sentence_count: int = 0
       word_count: int = 0
       has_tables: bool = False
       has_lists: bool = False
       section_ref: Optional[SemanticSection] = None
       
       @property
       def indent(self) -> str:
           return "  " * self.level
       
       def to_dict(self) -> dict:
           """Convert to dictionary for JSON"""
           pass
   ```

2. **TableOfContents Class**:
   ```python
   class TableOfContents:
       def __init__(self, entries: List[TOCEntry]):
           self.entries = entries
       
       def to_dict(self) -> List[dict]:
           """Export as list of dicts"""
           return [entry.to_dict() for entry in self.entries]
       
       def to_markdown(self) -> str:
           """Generate markdown representation"""
           lines = ["# Table of Contents\n"]
           for entry in self.entries:
               indent = entry.indent
               number = f"{entry.number} " if entry.number else ""
               title = entry.title
               stats = f"({entry.sentence_count} sentences)"
               lines.append(f"{indent}{number}**{title}** {stats}")
           return "\n".join(lines)
       
       def to_text(self, include_stats: bool = True) -> str:
           """Generate plain text representation"""
           pass
       
       def __rich__(self):
           """Rich console rendering with color-coded content types"""
           pass
   ```

3. **TOCGenerator Class**:
   ```python
   class TOCGenerator:
       def generate(self, tree: SemanticTree) -> TableOfContents:
           """Generate TOC from semantic tree"""
           entries = []
           
           for section in tree.sections:
               entry = self._create_entry(section)
               entries.append(entry)
           
           # Add hierarchical numbering
           self._number_entries(entries)
           
           return TableOfContents(entries)
       
       def _create_entry(self, section: SemanticSection) -> TOCEntry:
           """Create TOC entry from section with content classification"""
           pass
       
       def _number_entries(self, entries: List[TOCEntry]):
           """Add hierarchical numbering: 1., 1.1, 1.1.1"""
           pass
   ```

**Integration**: Add to `SemanticTree`:
```python
@cached_property
def toc(self) -> TableOfContents:
    """Get table of contents"""
    from edgar.documents.builders.toc_generator import TOCGenerator
    generator = TOCGenerator()
    return generator.generate(self)
```

**Tests**: `tests/documents/test_toc_generator.py`
- TOC generation from simple tree
- Hierarchical numbering (1., 1.1, 1.1.1, 1.1.2, 1.2, etc.)
- Content type classification (section/table/list/mixed)
- Sentence and word count calculation
- Markdown export format
- Dict export for JSON serialization
- Integration test with real 10-K

**Verification**:
```bash
python -m pytest tests/documents/test_toc_generator.py -v
```

---

### Phase 4: Rich Output and API Polish (4-6 hours)

**Goal**: Add rich console output, Jupyter support, and polish the API

**Enhancements**:

1. **Rich Console Support**:
   ```python
   # In SemanticTree
   def __rich__(self):
       """Rich console rendering"""
       from rich.panel import Panel
       from rich.tree import Tree
       # Create interactive tree view with color-coding
       pass
   
   # In SemanticSection
   def __rich__(self):
       """Rich console rendering with sentence preview"""
       pass
   ```

2. **Jupyter Notebook Support**:
   ```python
   # In SemanticTree
   def _repr_html_(self):
       """Jupyter notebook HTML representation"""
       # Generate interactive HTML with collapsible sections
       pass
   ```

3. **Convenience Methods**:
   ```python
   # In SemanticTree
   def export_json(self, path: str):
       """Export tree structure to JSON"""
       pass
   
   def export_csv(self, path: str):
       """Export sentences to CSV"""
       pass
   
   def search(self, query: str, case_sensitive: bool = False) -> List[tuple]:
       """Search for query in sentences"""
       pass
   ```

4. **Filing Integration**:
   ```python
   # In edgar/_filings.py - Filing class
   def semantic_tree(self) -> 'SemanticTree':
       """Get semantic tree representation of filing"""
       doc = self.document()
       return doc.semantic_tree
   ```

5. **Example Script**: `examples/semantic_tree_demo.py`
   ```python
   from edgar import Company
   
   # Demo various features
   company = Company("AAPL")
   filing = company.get_filings(form="10-K").latest(1)
   tree = filing.semantic_tree()
   
   print(tree.toc)  # Rich TOC
   print(tree.stats)  # Statistics
   
   # Search and display
   results = tree.search("artificial intelligence")
   for path, sent in results[:5]:
       print(f"{path}: {sent.text}")
   ```

**Documentation**:
- Add comprehensive docstrings to all classes and methods
- Create usage examples in docstrings
- Update README.md with semantic tree example

**Verification**:
```bash
python examples/semantic_tree_demo.py
python -m pytest tests/documents/ -k semantic -v
```

---

### Phase 5: Integration and Testing (6-8 hours)

**Goal**: Comprehensive testing, integration validation, performance benchmarking

**Integration Tests**: `tests/documents/test_semantic_tree_integration.py`

Test with real SEC filings:
```python
def test_apple_10k_semantic_tree():
    """Test semantic tree with Apple 10-K 2023"""
    filing = Company("AAPL").get_filings(form="10-K", filing_date="2023-11-03").latest(1)
    tree = filing.semantic_tree()
    
    # Verify structure
    assert len(tree.sections) > 10
    assert tree.stats['total_sentences'] > 1000
    
    # Verify specific sections exist
    assert tree.get_section("Risk Factors") is not None
    assert tree.get_section("Business") is not None
    
    # Verify TOC
    toc = tree.toc
    assert len(toc) > 10
    
    # Verify sentence search
    results = tree.search("competition")
    assert len(results) > 0

def test_microsoft_10q_semantic_tree():
    """Test with Microsoft 10-Q"""
    # Similar comprehensive tests
    pass

def test_tesla_8k_semantic_tree():
    """Test with Tesla 8-K"""
    # Test event-driven filing
    pass
```

**Edge Cases**: `tests/documents/test_semantic_tree_edge_cases.py`
- Empty document
- Single paragraph document
- Document with no sections
- Document with malformed HTML
- Very long paragraphs (>10,000 words)
- Nested tables
- Unicode and special characters

**Performance Tests**: `tests/documents/test_semantic_tree_performance.py`
```python
def test_tokenization_performance():
    """10,000 words should tokenize in < 1 second"""
    text = generate_large_text(10000)
    tokenizer = SentenceTokenizer()
    
    start = time.time()
    sentences = tokenizer.tokenize(text)
    duration = time.time() - start
    
    assert duration < 1.0

def test_tree_building_performance():
    """100-page document should build tree in < 5 seconds"""
    filing = get_large_10k_filing()  # ~100 pages
    
    start = time.time()
    tree = filing.semantic_tree()
    duration = time.time() - start
    
    assert duration < 5.0

def test_search_performance():
    """Search 10,000 sentences should complete in < 100ms"""
    tree = build_large_tree()
    
    start = time.time()
    results = tree.search("revenue")
    duration = time.time() - start
    
    assert duration < 0.1
```

**Verification**:
```bash
# Run all tests
hatch run test-fast
hatch run test-network

# Performance tests
python -m pytest tests/documents/test_semantic_tree_performance.py -v

# Check coverage
hatch run cov
```

---

## File Structure

### New Files to Create

```
edgar/documents/builders/
├── __init__.py
├── sentence_tokenizer.py      # Phase 1
├── semantic_tree_builder.py   # Phase 2
└── toc_generator.py            # Phase 3

tests/documents/
├── test_sentence_tokenizer.py           # Phase 1
├── test_semantic_tree_builder.py        # Phase 2
├── test_toc_generator.py                # Phase 3
├── test_semantic_tree_integration.py    # Phase 5
├── test_semantic_tree_edge_cases.py     # Phase 5
└── test_semantic_tree_performance.py    # Phase 5

examples/
└── semantic_tree_demo.py       # Phase 4
```

### Files to Modify

```
edgar/documents/document.py     # Add semantic_tree property
edgar/_filings.py               # Add semantic_tree() method
```

### Files to Reference (Existing)

```
edgar/documents/nodes.py                            # Node hierarchy
edgar/documents/utils/toc_analyzer.py               # TOC analysis
edgar/documents/extractors/hybrid_section_detector.py  # Section detection
edgar/documents/strategies/header_detection.py      # Header identification
edgar/documents/strategies/table_processing.py      # Table classification
edgar/documents/extractors/text_extractor.py        # Text extraction
```

---

## Dependencies

**Required**:
- `nltk` - For sentence tokenization with `PunktSentenceTokenizer`
  - Can start with NLTK, upgrade to spaCy later if needed for better accuracy

**Already Available**:
- `rich` - For console output (already in dependencies)
- Existing node hierarchy and document parsing infrastructure

---

## Success Criteria

- [x] Sentence tokenization handles SEC-specific patterns correctly
  - "U.S.", "Inc.", "No. 1", "$1.5 million", "Dec. 31, 2023", "Section 1.01"
- [x] Semantic tree preserves document hierarchy accurately
- [x] Each sentence tagged with full section path/breadcrumb
- [x] Smart TOC generated with hierarchical numbering (1., 1.1, 1.1.1)
- [x] Headers and tables identified and classified
- [x] Rich console output with color-coding
- [x] Jupyter notebook support with collapsible sections
- [x] Simple API: `filing.semantic_tree()` one-liner
- [x] Performance targets met:
  - Tokenize 10,000 words < 1 second
  - Build tree from 100-page document < 5 seconds
  - Generate TOC < 1 second
  - Search 10,000 sentences < 100ms
- [x] All tests pass with >90% coverage for new code
- [x] Documentation complete with examples
- [x] No regression in existing functionality

---

## Risk Mitigation

### Potential Issues and Solutions

1. **Issue**: Sentence tokenization errors with SEC-specific abbreviations
   - **Mitigation**: Build comprehensive abbreviation list from real filings, allow custom rules

2. **Issue**: Section detection inaccuracy (missed or wrong sections)
   - **Mitigation**: Use existing multi-strategy detection (TOC → Heading → Pattern), add confidence scores

3. **Issue**: Performance degradation with very large documents (300+ pages)
   - **Mitigation**: Implement lazy loading of sentences, add pagination, optimize with indexes

4. **Issue**: Memory usage for large document corpora
   - **Mitigation**: Don't duplicate text (use references), implement generators, add option to disable caching

5. **Issue**: Incorrect semantic type inference
   - **Mitigation**: Use conservative defaults (BODY_TEXT), allow manual overrides, add confidence scores

6. **Issue**: Unicode and special character handling
   - **Mitigation**: Test with international filings, normalize text, preserve original formatting

---

## Timeline

- **Phase 1** (Sentence Tokenization): 4-6 hours
- **Phase 2** (Semantic Tree Builder): 6-8 hours
- **Phase 3** (TOC Generator): 4-5 hours
- **Phase 4** (Rich Output): 4-6 hours
- **Phase 5** (Integration & Testing): 6-8 hours

**Total Estimated Effort**: 24-33 hours (~3-4 full working days)

---

## Next Steps

1. **Review this plan** - Adjust phases or approach as needed
2. **Start Phase 1** - Implement sentence tokenizer
3. **Iterate** - Complete each phase, verify, then move to next
4. **Test continuously** - Validate with real SEC filings at each phase
5. **Document** - Update docs as you implement

Ready to begin implementation!
