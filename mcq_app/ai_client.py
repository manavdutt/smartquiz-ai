import os
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY", "")

# App crash nahi hoga, bas Client create tab hoga jab key available ho
if _api_key:
    client = genai.Client(api_key=_api_key)
else:
    client = None
    print("Warning: GEMINI_API_KEY is not set in environment variables.")

MODELS_TO_TRY = [
    'gemini-2.5-flash',
    'gemini-2.5-flash-001',
    'gemini-2.0-flash-001',
]


def call_with_retry(contents, config=None, max_retries=2):
    """Gemini API call with model fallback + quota handling."""

    for model_name in MODELS_TO_TRY:
        for attempt in range(max_retries):
            try:
                kwargs = {'model': model_name, 'contents': contents}
                if config is not None:
                    kwargs['config'] = config
                response = client.models.generate_content(**kwargs)
                return response  # ✅ Success

            except Exception as e:
                error_str = str(e).lower()

                is_quota = any(x in error_str for x in [
                    '429', 'quota', 'rate limit', 'resource_exhausted'
                ])
                is_retryable = any(x in error_str for x in [
                    '503', 'unavailable', 'overload', '500',
                    'internal error', 'temporarily'
                ])

                if is_quota:
                    break

                if is_retryable and attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    continue

                break  # Next model try karo

    raise Exception("AI service temporarily unavailable. Please try again.")


def detect_domain(text):
    """Content ka domain detect karo."""
    t = text.lower()
    domains = {
        'coding': [
            'def ', 'class ', 'import ', 'function', 'return', 'variable',
            'array', 'loop', 'algorithm', 'syntax', 'compiler', 'runtime',
            'recursion', 'stack', 'queue', 'binary', 'sorting', 'api',
            'html', 'css', 'javascript', 'python', 'java', 'c++', 'react',
            'django', 'sql', 'http', 'rest', 'oop', 'inheritance', 'int ',
            'string', 'boolean', 'void', 'static', 'public', 'private',
            'debug', 'exception', 'null', 'pointer', 'complexity', 'o(n)',
        ],
        'math_science': [
            'theorem', 'formula', 'equation', 'integral', 'derivative',
            'matrix', 'vector', 'probability', 'statistics', 'calculus',
            'trigonometry', 'algebra', 'geometry', 'physics', 'chemistry',
            'molecule', 'atom', 'reaction', 'force', 'energy', 'momentum',
        ],
        'networking_cs': [
            'protocol', 'network', 'layer', 'osi', 'tcp', 'ip', 'udp',
            'router', 'switch', 'bandwidth', 'latency', 'topology',
            'lan', 'wan', 'man', 'mac', 'arp', 'dns', 'encryption',
            'firewall', 'subnet', 'packet', 'frame', 'hub', 'bridge',
        ],
        'language_grammar': [
            'grammar', 'tense', 'noun', 'verb', 'adjective', 'adverb',
            'pronoun', 'preposition', 'sentence', 'paragraph', 'essay',
            'metaphor', 'simile', 'vocabulary', 'literature', 'poetry',
        ],
    }
    scores = {d: sum(1 for kw in kws if kw in t) for d, kws in domains.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else 'general_theory'
