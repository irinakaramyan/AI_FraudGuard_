"""
Claude AI Assistant API  —  Multi-provider (Groq free / Anthropic paid)
-----------------------------------------------------------------------
POST /api/assistant/chat        — multi-turn conversation
GET  /api/assistant/status      — AI service health
GET  /api/assistant/suggestions — quick-question suggestions

Provider priority (first configured key wins):
  1. Groq  — FREE, uses llama-3.3-70b-versatile
  2. Anthropic — Paid, uses claude-opus-4-6

Security controls:
  • Query length bounded at 500 chars
  • Conversation history capped at 20 turns (40 messages)
  • Individual history messages capped at 2 000 chars each
  • Exception details logged server-side only (type+msg shown for debugging)
  • All endpoints require valid JWT
"""
import logging
import os

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.utils.security import safe_str

logger = logging.getLogger(__name__)

assistant_bp = Blueprint('assistant', __name__, url_prefix='/api/assistant')

# ─── Constants ────────────────────────────────────────────────────────────────
_MAX_HIST_TURNS = 20
_MSG_CAP        = 2000

# ─── System Prompt (shared across providers) ──────────────────────────────────
_SYSTEM_PROMPT = """You are FraudGuard AI, a friendly and knowledgeable assistant embedded in a professional fraud monitoring platform. You can talk about anything — casual conversation, general questions, and everyday topics are all welcome. Your primary specialisation is fraud detection and financial compliance, but you are happy to help with any question a user has.

When someone greets you or makes small talk (e.g. "hello", "how are you", "good morning"), respond naturally and warmly, like a helpful colleague would.

Your specialist areas (go deep when asked):
- **Transaction fraud** — card testing, account takeover, synthetic identity fraud, velocity attacks, triangulation fraud, friendly fraud
- **AML/CFT** — SAR filing thresholds and triggers, transaction monitoring rules, layering / structuring detection
- **KYC/CDD** — customer due diligence tiers, enhanced due diligence triggers, beneficial ownership rules
- **OFAC & Sanctions** — SDN list screening, fuzzy-match thresholds, blocked-person procedures, OFAC reporting obligations
- **PCI DSS** — cardholder data security controls, fraud monitoring requirements, incident response
- **Risk scoring** — Isolation Forest anomaly detection, combined risk score calculation, alert prioritisation
- **Compliance thresholds** — FinCEN $10,000 CTR rule, $5,000 SAR threshold, Reg E dispute timelines, chargeback ratios

Communication style:
- Match the tone of the question — casual for small talk, precise and structured for technical questions
- Use bullet points or numbered lists when enumerating items
- When citing regulations, include specific thresholds or rule references
- If uncertain, say so clearly rather than speculate
- Always be helpful — never refuse a question just because it is not fraud-related"""

# ─── Suggestion Cards ─────────────────────────────────────────────────────────
SUGGESTIONS = [
    {"category": "Fraud Patterns",  "text": "What are common velocity attack patterns?"},
    {"category": "Fraud Patterns",  "text": "How does card testing fraud work?"},
    {"category": "Fraud Patterns",  "text": "What is account takeover fraud?"},
    {"category": "Detection Rules", "text": "How is the combined risk score calculated?"},
    {"category": "Detection Rules", "text": "What triggers the HIGH_FREQUENCY rule?"},
    {"category": "Detection Rules", "text": "Explain the Isolation Forest ML model"},
    {"category": "Risk Scoring",    "text": "When should a CRITICAL alert be escalated?"},
    {"category": "Risk Scoring",    "text": "What is the recommended false positive rate?"},
    {"category": "Regulatory",      "text": "When do I need to file a SAR?"},
    {"category": "Regulatory",      "text": "What does PCI DSS require for fraud monitoring?"},
    {"category": "Regulatory",      "text": "Explain AML transaction reporting thresholds"},
]


# ─── Provider Detection ───────────────────────────────────────────────────────
def _detect_provider():
    """Return ('groq', key) or ('anthropic', key) — whichever is configured."""
    groq_key = os.environ.get('GROQ_API_KEY', '').strip()
    if groq_key and groq_key != 'your-groq-api-key-here':
        return 'groq', groq_key

    ant_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if ant_key and ant_key != 'your-anthropic-api-key-here':
        return 'anthropic', ant_key

    return None, None


def _provider_info():
    provider, _ = _detect_provider()
    if provider == 'groq':
        return {
            'provider':       'Groq (Free)',
            'model':          'llama-3.3-70b-versatile',
            'context_window': '128K tokens',
            'thinking':       'N/A',
        }
    if provider == 'anthropic':
        return {
            'provider':       'Anthropic',
            'model':          'claude-opus-4-6',
            'context_window': '200K tokens',
            'thinking':       'Adaptive',
        }
    return {
        'provider':       'None',
        'model':          '—',
        'context_window': '—',
        'thinking':       '—',
    }


# ─── Call Groq ────────────────────────────────────────────────────────────────
def _call_groq(api_key, messages):
    from groq import Groq
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model    = 'llama-3.3-70b-versatile',
        messages = [{'role': 'system', 'content': _SYSTEM_PROMPT}] + messages,
        max_tokens = 4096,
        temperature = 0.3,
    )
    answer = resp.choices[0].message.content.strip()
    model  = resp.model
    return answer, model


# ─── Call Anthropic ───────────────────────────────────────────────────────────
def _call_anthropic(api_key, messages):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model      = 'claude-opus-4-6',
        max_tokens = 4096,
        system     = _SYSTEM_PROMPT,
        messages   = messages,
    )
    answer = '\n\n'.join(
        b.text for b in resp.content if b.type == 'text'
    ).strip()
    model = resp.model
    return answer, model


# ─── POST /api/assistant/chat ─────────────────────────────────────────────────
@assistant_bp.route('/chat', methods=['POST'])
@jwt_required()
def chat():
    data    = request.get_json(silent=True) or {}
    query   = safe_str(data.get('query') or '', max_length=500)
    history = data.get('history') or []

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    provider, api_key = _detect_provider()
    if not provider:
        return jsonify({
            'answer':     (
                '⚠️ **No AI provider configured.**\n\n'
                'Add a free key to your `.env` file:\n'
                '- **Groq (free):** [console.groq.com](https://console.groq.com/) → set `GROQ_API_KEY`\n'
                '- **Anthropic (paid):** [console.anthropic.com](https://console.anthropic.com/) → set `ANTHROPIC_API_KEY`'
            ),
            'sources':    [],
            'confidence': 0.0,
            'intent':     'error',
        }), 200

    # ── Retrieve relevant documentation chunks (RAG) ─────────────────────────
    rag_context = ''
    try:
        from app.services.rag_service import rag_service
        if rag_service.loaded:
            rag_context = rag_service.get_context(query, top_k=3)
    except Exception:
        pass  # RAG failure must never block the chat

    # ── Build sanitised message list ──────────────────────────────────────────
    messages = []
    for msg in history[-(_MAX_HIST_TURNS * 2):]:
        role    = msg.get('role', '')
        content = str(msg.get('content', ''))[:_MSG_CAP]
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})

    # Inject RAG context directly into the user message when relevant docs exist
    if rag_context:
        user_content = (
            f'Relevant documentation from the FraudGuard project:\n\n'
            f'{rag_context}\n\n'
            f'---\n\n'
            f'User question: {query}'
        )
    else:
        user_content = query

    messages.append({'role': 'user', 'content': user_content})

    # ── Dispatch to provider ──────────────────────────────────────────────────
    try:
        if provider == 'groq':
            answer, model = _call_groq(api_key, messages)
        else:
            answer, model = _call_anthropic(api_key, messages)

        if not answer:
            answer = 'I processed your request but produced no visible output. Please try rephrasing.'

        return jsonify({
            'answer':     answer,
            'sources':    [],
            'confidence': 1.0,
            'intent':     'general',
            'model':      model,
        }), 200

    except Exception as e:
        logger.exception('AI provider (%s) error for query: %.80s', provider, query)
        err_type = type(e).__name__
        err_msg  = str(e)
        return jsonify({
            'answer':     f'⚠️ **{err_type}:** {err_msg}',
            'sources':    [],
            'confidence': 0.0,
            'intent':     'error',
        }), 200


# ─── GET /api/assistant/status ────────────────────────────────────────────────
@assistant_bp.route('/status', methods=['GET'])
@jwt_required()
def status():
    provider, _ = _detect_provider()
    info = _provider_info()
    return jsonify({
        'status':  'operational' if provider else 'error',
        'details': info,
    }), 200


# ─── GET /api/assistant/suggestions ──────────────────────────────────────────
@assistant_bp.route('/suggestions', methods=['GET'])
@jwt_required()
def suggestions():
    return jsonify(SUGGESTIONS), 200
