"""
Vector Store & Retrieval Engine for Smart BMS RAG Knowledge Base
Loads domain documents, chunks by section, and performs semantic search
using FAISS with Sentence-Transformers embeddings (plus TF-IDF cosine fallback).
"""

import os
import glob
import re
from typing import List, Dict, Any, Optional
import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


class DocumentChunk:
    def __init__(self, doc_id: str, title: str, section: str, text: str, chunk_index: int):
        self.doc_id = doc_id
        self.title = title
        self.section = section
        self.text = text.strip()
        self.chunk_index = chunk_index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": f"{self.doc_id}#sec-{self.chunk_index}",
            "doc_id": self.doc_id,
            "title": self.title,
            "section": self.section,
            "text": self.text,
        }


class KnowledgeBaseVectorStore:
    """
    Indexes battery technical documentation chunks into a FAISS vector index
    and provides semantic Top-K retrieval with relevance scoring.
    """

    def __init__(self, kb_dir: Optional[str] = None):
        if kb_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            kb_dir = os.path.join(current_dir, "knowledge_base")
        self.kb_dir = kb_dir

        self.chunks: List[DocumentChunk] = []
        self.faiss_index = None
        self.embeddings = None
        self.embed_dim = 384
        self.encoder = None
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.mode = "init"

        self._load_and_index()

    def _load_and_index(self):
        """Parse all markdown files in knowledge_base into section chunks."""
        self.chunks = []
        md_files = sorted(glob.glob(os.path.join(self.kb_dir, "*.md")))

        for filepath in md_files:
            filename = os.path.basename(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract main title
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            main_title = title_match.group(1).strip() if title_match else filename

            # Split into sections by '## '
            sections = re.split(r"\n(?=##\s+)", content)
            for idx, sec in enumerate(sections):
                sec_text = sec.strip()
                if not sec_text:
                    continue

                # Section header
                sec_match = re.search(r"^##\s+(.+)$", sec_text, re.MULTILINE)
                sec_title = sec_match.group(1).strip() if sec_match else f"Overview {idx + 1}"

                # Clean header line from chunk body
                body = re.sub(r"^##\s+.+$", "", sec_text, flags=re.MULTILINE).strip()
                if not body:
                    body = sec_text

                chunk = DocumentChunk(
                    doc_id=filename,
                    title=main_title,
                    section=sec_title,
                    text=f"### {main_title} > {sec_title}\n\n{body}",
                    chunk_index=idx
                )
                self.chunks.append(chunk)

        print(f"[RAG VectorStore] Indexed {len(self.chunks)} technical document chunks from {len(md_files)} files.")

        # Attempt Sentence-Transformers embedding with FAISS
        try:
            from sentence_transformers import SentenceTransformer
            print("[RAG VectorStore] Initializing SentenceTransformer ('all-MiniLM-L6-v2')...")
            self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
            texts = [c.text for c in self.chunks]
            embeddings = self.encoder.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            self.embeddings = embeddings.astype(np.float32)
            self.embed_dim = self.embeddings.shape[1]

            if FAISS_AVAILABLE:
                self.faiss_index = faiss.IndexFlatIP(self.embed_dim)  # Inner product for normalized vectors = cosine sim
                self.faiss_index.add(self.embeddings)
                self.mode = "FAISS_SENTENCE_TRANSFORMERS"
                print(f"[RAG VectorStore] FAISS Inner-Product Index ready ({self.faiss_index.ntotal} vectors).")
            else:
                self.mode = "NUMPY_COSINE_SENTENCE_TRANSFORMERS"
                print("[RAG VectorStore] FAISS not found; using NumPy cosine similarity.")
        except Exception as e:
            print(f"[RAG VectorStore] SentenceTransformer initialization note: {e}. Falling back to TF-IDF semantic index.")
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            self.tfidf_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            texts = [c.text for c in self.chunks]
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
            self.mode = "TFIDF_COSINE"
            print("[RAG VectorStore] TF-IDF semantic vector index successfully initialized.")

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """
        Search Top-K most relevant technical documentation chunks.
        Returns chunk dicts with exact citation metadata and relevance scores.
        """
        if not self.chunks:
            return []

        top_k = min(top_k, len(self.chunks))

        # Mode 1: FAISS with Sentence-Transformers
        if self.mode == "FAISS_SENTENCE_TRANSFORMERS" and self.faiss_index is not None and self.encoder is not None:
            try:
                q_emb = self.encoder.encode([query], convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
                distances, indices = self.faiss_index.search(q_emb, top_k)

                results = []
                for score, idx in zip(distances[0], indices[0]):
                    if idx < 0 or idx >= len(self.chunks):
                        continue
                    chunk_data = self.chunks[idx].to_dict()
                    chunk_data["score"] = round(float(score) * 100.0, 1)
                    results.append(chunk_data)
                return results
            except Exception as e:
                print(f"[RAG VectorStore] FAISS search error: {e}. Fallback to keyword matching.")

        # Mode 2: TF-IDF Cosine
        if self.tfidf_vectorizer is not None and self.tfidf_matrix is not None:
            from sklearn.metrics.pairwise import cosine_similarity
            q_vec = self.tfidf_vectorizer.transform([query])
            sims = cosine_similarity(q_vec, self.tfidf_matrix)[0]
            top_indices = np.argsort(sims)[::-1][:top_k]

            results = []
            for idx in top_indices:
                score = float(sims[idx])
                chunk_data = self.chunks[idx].to_dict()
                chunk_data["score"] = round(score * 100.0, 1)
                results.append(chunk_data)
            return results

        # Mode 3: Simple word overlap fallback
        q_words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for c in self.chunks:
            c_words = set(re.findall(r"\w+", c.text.lower()))
            common = len(q_words.intersection(c_words))
            scored.append((common, c))
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {**c.to_dict(), "score": round(float(score) * 10.0, 1)}
            for score, c in scored[:top_k]
        ]


# Singleton instance
_vector_store_instance: Optional[KnowledgeBaseVectorStore] = None


def get_vector_store() -> KnowledgeBaseVectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = KnowledgeBaseVectorStore()
    return _vector_store_instance
