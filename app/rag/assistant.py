"""
RAG AI Assistant — Fraud Analysis Engine
─────────────────────────────────────────
Orchestrates retrieval + context-aware response generation.
Produces structured, professional responses grounded in the
fraud-detection knowledge base — no external LLM API required.
"""

import re
import logging
import textwrap
from datetime import datetime

from app.rag.knowledge_base import load_documents
from app.rag.retriever import FraudKnowledgeRetriever

logger = logging.getLogger(__name__)

# ── Singleton initialiser ─────────────────────────────────────────────────────
_assistant_instance = None

def get_assistant() -> 'FraudAssistant':
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = FraudAssistant()
    return _assistant_instance


# ── Response Templates ────────────────────────────────────────────────────────
_GREETING_PATTERNS = re.compile(
    r'\b(hi|hello|hey|greetings|good\s*(morning|afternoon|evening))\b', re.I)

_THANK_PATTERNS = re.compile(
    r'\b(thank(s| you)|thx|cheers)\b', re.I)

_GREETING_RESPONSE = (
    "Hello! I'm **FraudGuard AI Assistant**, your expert on financial fraud detection. "
    "I can help you with:\n\n"
    "- 🔍 **Fraud Patterns** — velocity attacks, card testing, account takeover\n"
    "- ⚙️ **Detection Rules** — thresholds, weights, risk score interpretation\n"
    "- 📋 **Regulatory Compliance** — AML, PCI DSS, BSA, FATF guidelines\n"
    "- 📊 **Risk Scoring** — understanding combined scores and recommended actions\n\n"
    "What would you like to know?"
)

_FALLBACK_RESPONSE = (
    "I couldn't find a specific answer in my knowledge base for that query. "
    "Please try rephrasing your question, or ask about:\n\n"
    "- Fraud patterns (velocity, card testing, ATO, CNP fraud)\n"
    "- Detection rules and thresholds\n"
    "- Risk score interpretation\n"
    "- Regulatory requirements (AML, PCI DSS)\n"
    "- Alert prioritisation and investigation steps"
)

# Question intent → category hints
_INTENT_MAP = [
    (re.compile(r'\b(pattern|attack|velocity|carding|ato|cnp|mule|synthetic)\b', re.I), 'fraud_patterns'),
    (re.compile(r'\b(rule|threshold|weight|score|flag|block|iso(lation)?\s*forest|model|ml)\b', re.I), 'detection_rules'),
    (re.compile(r'\b(comply|compliance|regulation|gdpr|pci|aml|bsa|fatf|sar|ctr|kyc)\b', re.I), 'regulatory'),
    (re.compile(r'\b(risk\s*score|kpi|benchmark|false\s*positive|precision|recall|interpret)\b', re.I), 'risk_scoring'),
]


class FraudAssistant:
    """
    RAG-powered fraud analysis assistant.

    Pipeline:
        query → intent detection → retrieval → context assembly → response generation
    """

    def __init__(self):
        logger.info('Initialising FraudAssistant …')
        docs = load_documents()
        self.retriever = FraudKnowledgeRetriever(docs)
        self._conversation_turns = 0
        logger.info('FraudAssistant ready (%d knowledge chunks)', len(docs))

    # ── Public API ─────────────────────────────────────────────────────────────
    def ask(self, query: str, context: dict | None = None) -> dict:
        """
        Main entry point.

        Args:
            query:   User's natural-language question
            context: Optional transaction/alert context dict

        Returns:
            {
                answer     : str   — formatted markdown response
                sources    : list  — cited document titles
                confidence : float — 0.0–1.0
                intent     : str   — detected question category
                chunks     : int   — number of retrieved chunks
            }
        """
        query = query.strip()
        self._conversation_turns += 1

        # ── Handle greetings / thanks ──────────────────────────────────────────
        if _GREETING_PATTERNS.search(query):
            return self._wrap(_GREETING_RESPONSE, [], 1.0, 'greeting', 0)
        if _THANK_PATTERNS.search(query):
            return self._wrap(
                "You're welcome! Feel free to ask any other questions about fraud detection, "
                "risk scoring, or regulatory compliance.",
                [], 0.9, 'acknowledgement', 0
            )

        # ── Detect intent ──────────────────────────────────────────────────────
        intent = self._detect_intent(query)

        # ── Retrieve relevant chunks ───────────────────────────────────────────
        results = self.retriever.retrieve(query, top_k=4)

        if not results:
            return self._wrap(_FALLBACK_RESPONSE, [], 0.0, intent, 0)

        # ── Generate response ──────────────────────────────────────────────────
        answer     = self._generate(query, results, context, intent)
        sources    = list({r['document']['title'] for r in results})
        confidence = min(1.0, results[0]['score'] * 5.5) if results else 0.0

        return self._wrap(answer, sources, confidence, intent, len(results))

    # ── Intent Detection ───────────────────────────────────────────────────────
    def _detect_intent(self, query: str) -> str:
        for pattern, category in _INTENT_MAP:
            if pattern.search(query):
                return category
        return 'general'

    # ── Response Generator ─────────────────────────────────────────────────────
    def _generate(self, query: str, results: list, context: dict | None, intent: str) -> str:
        # Build context block from top retrieved chunks
        ctx_parts = []
        for r in results[:3]:
            doc  = r['document']
            text = doc['content'][:600].strip()
            ctx_parts.append(f"**{doc['heading']}**\n{text}")

        ctx_block = '\n\n---\n\n'.join(ctx_parts)

        # Generate intent-specific preamble
        preamble = self._intent_preamble(intent, query)

        # Extract key bullet points from context
        bullets   = self._extract_bullets(results)
        bullet_md = '\n'.join(f'- {b}' for b in bullets[:6]) if bullets else ''

        # Build response sections
        sections = [preamble]

        if bullet_md:
            sections.append(bullet_md)

        # Add detailed context excerpt
        if results:
            top_doc     = results[0]['document']
            detail_text = top_doc['content'][:800].strip()
            sections.append(f"\n**Detailed Analysis** *(from: {top_doc['heading']})*\n\n{detail_text}")

        # Add transaction-specific commentary if context provided
        if context:
            sections.append(self._transaction_commentary(context, results))

        # Add actionable recommendation
        sections.append(self._recommendation(intent, results))

        return '\n\n'.join(s for s in sections if s)

    def _intent_preamble(self, intent: str, query: str) -> str:
        preambles = {
            'fraud_patterns' : "Based on the fraud detection knowledge base, here is what you need to know about this fraud pattern:",
            'detection_rules': "Here is a detailed explanation of the detection rules and their methodology:",
            'regulatory'     : "Based on current regulatory frameworks applicable to financial fraud detection:",
            'risk_scoring'   : "Here is the risk scoring methodology and how to interpret the results:",
            'general'        : "Based on the fraud detection knowledge base:",
        }
        return preambles.get(intent, preambles['general'])

    def _extract_bullets(self, results: list) -> list[str]:
        """Extract key sentences from retrieved documents as bullet points."""
        bullets = []
        seen    = set()

        for r in results[:3]:
            content = r['document']['content']
            # Extract sentences that look like key indicators
            for line in content.split('\n'):
                line = line.strip().lstrip('- •*').strip()
                if (len(line) > 30 and len(line) < 180
                        and line not in seen
                        and not line.startswith('#')
                        and not line.startswith('TITLE')
                        and not line.startswith('CATEGORY')):
                    bullets.append(line)
                    seen.add(line)
                    if len(bullets) >= 8:
                        break
            if len(bullets) >= 8:
                break

        return bullets

    def _transaction_commentary(self, context: dict, results: list) -> str:
        """Generate commentary specific to a given transaction context."""
        parts = ["\n**Transaction Context Analysis**"]

        amount    = context.get('amount', 0)
        status    = context.get('status', '')
        risk      = context.get('risk_score', 0)
        location  = context.get('location', '')
        category  = context.get('merchant_category', '')

        if amount > 10000:
            parts.append(f"⚠️ Transaction amount of **${amount:,.2f}** exceeds the $10,000 high-risk threshold. This triggers the LARGE_AMOUNT rule and may require CTR filing under BSA requirements.")
        if status == 'blocked':
            parts.append("🚫 This transaction has been **blocked** — risk score exceeds the 0.80 critical threshold. Immediate analyst review is recommended.")
        elif status == 'flagged':
            parts.append("⚠️ This transaction is **flagged** — risk score is between 0.50 and 0.80. Step-up authentication is recommended before processing.")
        if location and location not in ('US', 'CA', 'UK', 'AU', 'DE', 'FR'):
            parts.append(f"🌍 International transaction from **{location}** detected. Enhanced due diligence applies per FATF Recommendation 10.")
        if category in ('gambling', 'cryptocurrency', 'money_transfer'):
            parts.append(f"⚡ High-risk merchant category **{category}** detected. These categories have elevated fraud and money-laundering risk profiles.")
        if risk > 0.7:
            parts.append(f"📊 Combined risk score of **{risk:.1%}** indicates a **critical risk** level. Recommend immediate escalation.")

        return '\n'.join(parts)

    def _recommendation(self, intent: str, results: list) -> str:
        """Append a short recommended action section."""
        recommendations = {
            'fraud_patterns' : (
                "\n**Recommended Actions**\n"
                "1. Review transaction history for the customer over the last 24 hours\n"
                "2. Check if the pattern matches any open alerts in the system\n"
                "3. Initiate step-up authentication if the customer is reachable\n"
                "4. Document findings in the alert resolution notes"
            ),
            'detection_rules': (
                "\n**Recommended Actions**\n"
                "1. Review the triggered rules in the Risk Analysis section of the transaction\n"
                "2. Compare rule score vs ML score — discordance may indicate a model blind spot\n"
                "3. Consider adjusting rule thresholds via the Detection Rules page if false positives are high"
            ),
            'regulatory'     : (
                "\n**Compliance Reminder**\n"
                "1. File SAR if suspicious activity confirmed — deadline is 30 days from detection\n"
                "2. Document all investigation steps for audit trail\n"
                "3. Consult your BSA/AML compliance officer for borderline cases"
            ),
            'risk_scoring'   : (
                "\n**Interpretation Guide**\n"
                "- Score < 0.30: Approve — no action needed\n"
                "- Score 0.30–0.50: Monitor — watch for pattern development\n"
                "- Score 0.50–0.75: Flag — analyst review required\n"
                "- Score > 0.75: Block — immediate escalation required"
            ),
        }
        return recommendations.get(intent, '')

    # ── Helper ─────────────────────────────────────────────────────────────────
    def _wrap(self, answer: str, sources: list, confidence: float, intent: str, chunks: int) -> dict:
        return {
            'answer'     : answer,
            'sources'    : sources,
            'confidence' : round(confidence, 3),
            'intent'     : intent,
            'chunks'     : chunks,
            'timestamp'  : datetime.utcnow().isoformat(),
        }

    def stats(self) -> dict:
        return {
            'index_stats'        : self.retriever.index_stats(),
            'conversation_turns' : self._conversation_turns,
        }
