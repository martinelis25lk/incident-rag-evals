import os
import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from rank_bm25 import BM25Okapi

from src.ingest import load_and_chunk_documents, COLLECTION_NAME, DATA_DIR

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class HybridIncidentRetriever:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=COLLECTION_NAME,
            connection=DATABASE_URL,
            use_jsonb=True,
        )
        self.corpus_docs: list[Document] = load_and_chunk_documents(Path(DATA_DIR))
        tokenized_corpus = [_tokenize(doc.page_content) for doc in self.corpus_docs]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def _bm25_search(self, query: str, k: int, company: Optional[str] = None) -> list[Document]:
        tokenized_query = _tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        scored_docs = []
        for doc, score in zip(self.corpus_docs, scores):
            if company and str(doc.metadata.get("company", "")).lower() != company.lower():
                continue
            scored_docs.append((doc, float(score)))

        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, score in scored_docs[:k] if score > 0]

    def _vector_search(self, query: str, k: int, company: Optional[str] = None) -> list[Document]:
        search_kwargs = {"k": k}
        if company:
            search_kwargs["filter"] = {"company": company}
        return self.vector_store.similarity_search(query, **search_kwargs)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        company: Optional[str] = None,
        rrf_k: int = 60,
    ) -> list[Document]:
        """Combina resultados vetoriais e BM25 via Reciprocal Rank Fusion (RRF)."""
        candidate_k = top_k * 2
        vector_docs = self._vector_search(query, k=candidate_k, company=company)
        bm25_docs = self._bm25_search(query, k=candidate_k, company=company)

        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for rank, doc in enumerate(vector_docs, start=1):
            key = doc.page_content
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)

        for rank, doc in enumerate(bm25_docs, start=1):
            key = doc.page_content
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)

        ranked_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        return [doc_map[k] for k in ranked_keys[:top_k]]
