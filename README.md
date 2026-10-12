# Enterprise RAG Knowledge Assistant

A personal project exploring the design of an **enterprise Retrieval-Augmented Generation (RAG) system** for processing and retrieving information from multi-format company documents.

The project is built to understand the RAG pipeline in depth instead of relying heavily on high-level RAG frameworks.

---

## Project Goal

The goal is to build a RAG system that can process enterprise documents such as:

- SOPs
- Company policies
- Technical documents
- Product information
- Troubleshooting guides
- Structured tables and lists

and retrieve the most relevant information for a user's question before passing the context to a local LLM.

---

## Current Pipeline

```text
Enterprise Documents
        ↓
Document Parsing
        ↓
Normalization
        ↓
Chunking
        ↓
Embeddings
        ↓
Retrieval
        ↓
Local LLM
        ↓
Answer + Citation
```

The project is currently focused mainly on the **document processing and chunking stages**.

---

## Supported Document Formats

The current pipeline supports:

- HTML
- Markdown
- PDF
- DOCX
- PPTX

All formats are converted into a common normalized document structure before chunking.

---

## Document Normalization

The normalization layer preserves useful information such as:

- Text
- Heading hierarchy
- Lists
- Nested lists
- Tables
- Document order
- Page numbers
- Slide numbers
- Source metadata

while ignoring presentation-only information such as styling and decorative layout.

---

## Chunking Strategies

Several chunking approaches were implemented and tested to understand how different strategies affect chunk size and document structure.

Implemented strategies include:

- Fixed-size chunking
- Sliding-window chunking
- Line-based chunking
- Page / Slide chunking
- Adaptive Page / Slide chunking
- Recursive chunking
- Semantic chunking
- Hierarchical / Parent-Child chunking

---

## Dataset

This project uses the **RAG-Multi-Corpus** dataset:

https://github.com/udayallu/RAG-Multi-Corpus.git

The dataset itself is not included in this repository.

The corpus used during development contains:

| Format | Files |
|---|---:|
| HTML | 236 |
| Markdown | 236 |
| PDF | 236 |
| DOCX | 236 |
| PPTX | 236 |
| **Total** | **1,180** |

---

## Local Embeddings

Semantic chunking currently uses:

```text
LM Studio
+
text-embedding-nomic-embed-text-v1.5@q8_0
```

The embedding model runs locally through the LM Studio API.

This keeps the embedding process local and allows me to experiment with different embedding and retrieval configurations later.

---

## Python Environment

Recommended:

```text
Python 3.12
```

Current libraries:

```text
pydantic
numpy==1.26.4
requests
tiktoken
beautifulsoup4
python-docx
python-pptx
PyMuPDF
```

Install dependencies using:

```bash
pip install -r requirements.txt
```

---

# Project Direction

After completing the chunking stage, I plan to continue building the RAG pipeline step by step.

## 1. Embeddings

I will continue experimenting with:

- Document embeddings
- Query embeddings
- Embedding configurations for retrieval

Current embedding model:

```text
text-embedding-nomic-embed-text-v1.5@q8_0
```

---

## 2. Vector Database

I plan to use:

```text
PostgreSQL
+
pgvector
```

The database will store:

- Chunks
- Embeddings
- Document metadata
- Source information
- Parent-child relationships

---

## 3. Retrieval

I plan to experiment with several retrieval techniques:

```text
User Query
    ↓
Query Preprocessing
    ↓
Metadata Filtering
    ↓
Dense Vector Search
    ↓
Keyword Search
    ↓
Hybrid Fusion
    ↓
Reranking
```

The goal is to compare different retrieval approaches instead of assuming one method performs best.

---

## 4. Local LLM

For answer generation, I plan to continue using:

```text
LM Studio
```

The LLM will receive retrieved document context and generate answers based on the available enterprise knowledge.

Later stages will explore:

- Source citations
- Unsupported-answer detection
- Context quality
- Hallucination reduction

---

## 5. Evaluation

I plan to evaluate both retrieval quality and overall system performance.

### Retrieval

- Recall@K
- MRR
- nDCG@K
- Supporting-fact retrieval

### System

- Query failures
- Retrieval failures
- Retrieval scores
- Retrieval latency
- LLM latency
- Model performance comparison

### User Evaluation

- Incorrect answers
- Missing information
- Failed queries

The goal is to understand **why a query fails**, rather than only checking whether the final answer looks correct.

---

# Optional Later Development

After the main RAG pipeline is working, I may also add:

## Backend

- FastAPI
- REST API

## Frontend

- React / Next.js

## Deployment

- Docker
- PostgreSQL deployment
- API deployment
- Local or cloud hosting

These are secondary to the main RAG and retrieval work.
