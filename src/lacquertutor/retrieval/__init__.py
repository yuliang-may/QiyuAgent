"""Retrieval pipeline for LacquerTutor.

Implements the paper's hybrid retrieval architecture:
  BM25 (sparse) + Dense (Qwen text-embedding-v3) → Merge → Rerank (gte-rerank) → top-k

Supports two backends:
  - VectorEvidenceStore: Qdrant-backed with real embeddings (production)
  - EvidenceStore: In-memory metadata-based filtering (fallback/testing)
"""
