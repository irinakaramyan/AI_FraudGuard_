"""
RAG Knowledge Base — Document Loader
─────────────────────────────────────
Loads fraud-detection knowledge documents from the /knowledge/ folder,
chunks them into sections, and exposes them to the retriever.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ── Document Loader ────────────────────────────────────────────────────────────

def load_documents(knowledge_dir: str = None) -> list[dict]:
    """
    Load all .txt knowledge files from the knowledge directory.
    Each file is split into section chunks for fine-grained retrieval.
    Returns a list of document dicts with keys: id, title, category, content, source.
    """
    if knowledge_dir is None:
        # Default: <project_root>/knowledge/
        knowledge_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'knowledge'
        )

    if not os.path.isdir(knowledge_dir):
        logger.warning('Knowledge directory not found: %s', knowledge_dir)
        return _get_builtin_documents()

    documents = []
    doc_id = 0

    for fname in sorted(os.listdir(knowledge_dir)):
        if not fname.endswith('.txt'):
            continue
        fpath = os.path.join(knowledge_dir, fname)
        try:
            with open(fpath, encoding='utf-8') as f:
                raw = f.read().strip()

            # Parse header metadata
            title    = _extract_field(raw, 'TITLE')    or fname.replace('.txt', '').replace('_', ' ').title()
            category = _extract_field(raw, 'CATEGORY') or 'general'

            # Remove header lines
            body = re.sub(r'^(TITLE|CATEGORY):.*$', '', raw, flags=re.MULTILINE).strip()

            # Split into ## sections
            sections = _split_sections(body, title, category)
            for s in sections:
                s['id'] = doc_id
                s['source'] = fname
                documents.append(s)
                doc_id += 1

            logger.info('Loaded %d chunks from %s', len(sections), fname)

        except Exception as e:
            logger.error('Failed to load %s: %s', fname, e)

    if not documents:
        logger.warning('No documents loaded from disk — using built-in fallback.')
        return _get_builtin_documents()

    logger.info('Knowledge base ready: %d total chunks from %s files', doc_id, len([f for f in os.listdir(knowledge_dir) if f.endswith('.txt')]))
    return documents


def _extract_field(text: str, field: str) -> str:
    m = re.search(rf'^{field}:\s*(.+)$', text, re.MULTILINE)
    return m.group(1).strip() if m else ''


def _split_sections(body: str, file_title: str, category: str) -> list[dict]:
    """Split document body by ## headings into chunks."""
    parts   = re.split(r'\n## ', body)
    chunks  = []

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        lines   = part.split('\n', 1)
        heading = lines[0].lstrip('# ').strip() if lines else f'Section {i+1}'
        content = lines[1].strip() if len(lines) > 1 else part

        chunks.append({
            'title'    : f'{file_title} — {heading}',
            'heading'  : heading,
            'category' : category,
            'content'  : f'{heading}\n{content}',
        })

    # If no ## headings found, treat the whole body as one chunk
    if not chunks and body:
        chunks.append({
            'title'    : file_title,
            'heading'  : file_title,
            'category' : category,
            'content'  : body,
        })

    return chunks


# ── Built-in fallback documents (in case /knowledge/ dir is missing) ──────────
def _get_builtin_documents() -> list[dict]:
    return [
        {
            'id': 0, 'source': 'builtin', 'category': 'fraud_patterns',
            'title': 'Velocity Attacks',
            'heading': 'Velocity Attacks',
            'content': 'Velocity attacks occur when fraudsters make many transactions in a short timeframe. Key indicators: more than 5 transactions within 60 minutes, multiple small transactions followed by one large transaction, rapid succession of declined transactions before an approved one.',
        },
        {
            'id': 1, 'source': 'builtin', 'category': 'detection_rules',
            'title': 'Risk Score Interpretation',
            'heading': 'Risk Score Interpretation',
            'content': 'Risk scores range 0.0-1.0. LOW (<0.30): approve. MEDIUM (0.30-0.49): monitor. HIGH (0.50-0.74): flag for review. CRITICAL (>0.75): block immediately. Combined score = 0.40 x rule_score + 0.60 x ml_score.',
        },
        {
            'id': 2, 'source': 'builtin', 'category': 'regulatory',
            'title': 'AML Reporting',
            'heading': 'AML Reporting',
            'content': 'File Currency Transaction Reports (CTR) for cash transactions exceeding $10,000. File Suspicious Activity Reports (SAR) within 30 days of detecting suspicious activity. Maintain transaction records for 5 years.',
        },
    ]
