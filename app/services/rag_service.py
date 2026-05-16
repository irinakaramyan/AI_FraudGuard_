"""
RAG Service — Retrieval-Augmented Generation
─────────────────────────────────────────────
Loads all markdown documents from the docs/ folder at startup,
splits them into sections, and retrieves the most relevant chunks
for a given query using keyword overlap scoring (TF-IDF-like).

Usage:
    from app.services.rag_service import rag_service
    rag_service.load('/path/to/docs')
    context = rag_service.get_context("What is the OFAC threshold?")
"""

import re
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


# ─── Stop words (ignored during scoring) ──────────────────────────────────────
_STOP_WORDS = {
    'the', 'and', 'for', 'are', 'this', 'that', 'with', 'from', 'have',
    'has', 'was', 'were', 'will', 'shall', 'can', 'may', 'not', 'but',
    'all', 'each', 'its', 'also', 'any', 'per', 'they', 'their', 'then',
    'than', 'when', 'where', 'which', 'who', 'how', 'what', 'does', 'into',
    'been', 'being', 'should', 'would', 'could', 'must', 'our', 'your',
    'use', 'used', 'using', 'via', 'both', 'more', 'most', 'such', 'only',
}


class _Chunk:
    """A single document chunk with pre-computed token set."""

    __slots__ = ('source', 'section', 'content', 'tokens')

    def __init__(self, source: str, section: str, content: str):
        self.source  = source
        self.section = section
        self.content = content
        self.tokens  = _tokenize(content + ' ' + section)


def _tokenize(text: str) -> set:
    """Lowercase, strip punctuation, remove stop words, return set of tokens."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return {w for w in text.split() if len(w) > 2 and w not in _STOP_WORDS}


class RAGService:
    """
    Simple keyword-based RAG for project documentation.

    At startup:  call load(docs_dir)  — reads all .md files, splits by heading
    Per request: call get_context(query) — returns top-3 relevant chunks as a
                 formatted string ready to inject into the LLM prompt
    """

    def __init__(self):
        self._chunks: List[_Chunk] = []
        self.loaded = False

    # ── Startup ────────────────────────────────────────────────────────────────

    def load(self, docs_dir: str) -> None:
        """Load and chunk all markdown files under docs_dir (recursive)."""
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            logger.warning('RAG: docs directory not found: %s', docs_dir)
            return

        total = 0
        for md_file in sorted(docs_path.rglob('*.md')):
            try:
                text   = md_file.read_text(encoding='utf-8', errors='replace')
                chunks = self._split(md_file.name, text)
                self._chunks.extend(chunks)
                total += len(chunks)
            except Exception as exc:
                logger.warning('RAG: skipping %s — %s', md_file.name, exc)

        self.loaded = True
        logger.info('RAG: indexed %d chunks from %s', total, docs_dir)

    def _split(self, source: str, text: str) -> List[_Chunk]:
        """Split markdown into chunks at every heading (# / ## / ###)."""
        chunks  = []
        # Split on lines that start with one or more '#'
        sections = re.split(r'\n(?=#{1,4} )', text)

        for section in sections:
            if not section.strip():
                continue

            lines   = section.strip().splitlines()
            title   = lines[0].lstrip('#').strip() if lines else 'Section'
            content = '\n'.join(lines[1:]).strip()

            if not content:
                continue

            # If the section is very long, break it into paragraph-sized pieces
            if len(content) > 1200:
                paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                for idx, para in enumerate(paragraphs, 1):
                    chunks.append(_Chunk(source, f'{title} ({idx})', para))
            else:
                chunks.append(_Chunk(source, title, content))

        return chunks

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 3) -> List[Tuple[_Chunk, float]]:
        """Return the top_k most relevant chunks for the query."""
        if not self._chunks:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        scored = []
        for chunk in self._chunks:
            if not chunk.tokens:
                continue
            # Jaccard similarity: |intersection| / |union|
            inter = len(q_tokens & chunk.tokens)
            if inter == 0:
                continue
            union = len(q_tokens | chunk.tokens)
            score = inter / union
            scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_context(self, query: str, top_k: int = 3) -> str:
        """
        Return a formatted context block for injection into the LLM prompt.
        Returns an empty string if no relevant chunks are found.
        """
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return ''

        parts = []
        for chunk, _score in results:
            parts.append(
                f'[Source: {chunk.source} — {chunk.section}]\n{chunk.content}'
            )

        return '\n\n---\n\n'.join(parts)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


# ── Singleton (imported by assistant.py and __init__.py) ──────────────────────
rag_service = RAGService()
