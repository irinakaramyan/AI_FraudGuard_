"""
RAG Retriever — TF-IDF Vector Search
──────────────────────────────────────
Converts knowledge documents into TF-IDF vectors and finds
the most semantically similar chunks for any natural-language query.
No external API or GPU required — runs entirely on sklearn.
"""

import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class FraudKnowledgeRetriever:
    """
    TF-IDF retriever over the fraud-detection knowledge base.

    Usage:
        retriever = FraudKnowledgeRetriever(documents)
        results   = retriever.retrieve("what is velocity fraud?", top_k=3)
    """

    def __init__(self, documents: list[dict]):
        self.documents = documents
        self._build_index(documents)

    # ── Index Construction ─────────────────────────────────────────────────────
    def _build_index(self, documents: list[dict]):
        """Fit TF-IDF vectorizer on all document content."""
        if not documents:
            logger.warning('No documents to index.')
            self.vectorizer = None
            self.doc_vectors = None
            return

        corpus = [d['content'] for d in documents]

        self.vectorizer = TfidfVectorizer(
            max_features  = 8000,
            stop_words    = 'english',
            ngram_range   = (1, 3),     # Unigrams, bigrams, trigrams
            sublinear_tf  = True,       # Apply log(1+tf) scaling
            min_df        = 1,
            analyzer      = 'word',
        )

        self.doc_vectors = self.vectorizer.fit_transform(corpus)
        logger.info('TF-IDF index built: %d documents, %d features',
                    len(documents), self.doc_vectors.shape[1])

    # ── Retrieval ──────────────────────────────────────────────────────────────
    def retrieve(self, query: str, top_k: int = 4, min_score: float = 0.02) -> list[dict]:
        """
        Find the top_k most relevant document chunks for a query.

        Returns list of dicts:
            { document, score, rank }
        """
        if not self.vectorizer or self.doc_vectors is None:
            return []

        try:
            query_vec   = self.vectorizer.transform([query.lower()])
            sims        = cosine_similarity(query_vec, self.doc_vectors)[0]
            top_indices = np.argsort(sims)[::-1][:top_k]

            results = []
            for rank, idx in enumerate(top_indices):
                score = float(sims[idx])
                if score < min_score:
                    break
                results.append({
                    'document' : self.documents[idx],
                    'score'    : round(score, 4),
                    'rank'     : rank + 1,
                })

            return results

        except Exception as e:
            logger.error('Retrieval error: %s', e)
            return []

    # ── Diagnostic ─────────────────────────────────────────────────────────────
    def index_stats(self) -> dict:
        return {
            'total_documents' : len(self.documents),
            'features'        : self.doc_vectors.shape[1] if self.doc_vectors is not None else 0,
            'categories'      : list({d['category'] for d in self.documents}),
        }
