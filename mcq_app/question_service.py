import json
from typing import List
from pydantic import BaseModel, Field
from google.genai import types
from .ai_client import client, call_with_retry, detect_domain


# ─────────────────────────────────────────────────────────────
#  STRUCTURED JSON SCHEMA (FOR DJANGO DB ALIGNMENT)
# ─────────────────────────────────────────────────────────────
class QuestionItem(BaseModel):
    question: str = Field(description="The question text, question statement, or sentence with a blank '_____'.")
    answer: str = Field(description="The correct answer, absolute truth statement, or complete answer response.")
    wrong_option: str = Field(description="One highly plausible wrong choice/distractor. Mandatory for 'fitb'. Keep empty string '' for tf, vsq, sq, lq if not applicable.")
    explanation: str = Field(description="Compulsory 2-3 sentences explanation containing correct reason, misconception check, and key takeaway.")


class QuestionSetSchema(BaseModel):
    title: str = Field(description="Crisp topic or chapter name derived from the context content (maximum 6 words).")
    questions: List[QuestionItem]


# ─────────────────────────────────────────────────────────────
#  TYPE CONFIGS
# ─────────────────────────────────────────────────────────────
TYPE_CONFIGS = {
    'fitb': {
        'name': 'Fill in the Blanks',
        'instruction': (
            'Each question is a sentence with ONE blank shown as "_____". '
            'Also provide: correct answer AND one wrong/distractor option. '
            'Wrong option must be plausible — same category as correct answer '
            '(e.g. if answer is a number, wrong should also be a number). '
            'In JSON, return: "question", "answer" (correct), "wrong_option" (one wrong choice).'
        ),
        'answer_note': 'exact word or short phrase (1-5 words)',
        'difficulty_rules': {
            'beginner': 'Direct recall only — facts, definitions, simple identification. Anyone who read the content once can answer. Zero analysis or inference.',
            'advance': 'Important exam-level questions — understanding and application based. How/why/compare type. Focus on high-weightage concepts serious students must know.',
            'expert': 'Hardest questions only — edge cases, exceptions, traps, multi-concept synthesis. Zero easy questions. Only what separates toppers from average students.',
        },
    },
    'tf': {
        'name': 'True / False',
        'instruction': (
            'Each question is a clear declarative statement — either factually True or False based on the content. '
            'False statements should be plausible but contain one specific inaccuracy. '
            'Never make the false statement obviously wrong — it should require careful thought.'
        ),
        'answer_note': '"True" or "False"',
        'difficulty_rules': {
            'beginner': 'Direct recall only — facts, definitions, simple identification. Anyone who read the content once can answer. Zero analysis or inference.',
            'advance': 'Important exam-level questions — understanding and application based. How/why/compare type. Focus on high-weightage concepts serious students must know.',
            'expert': 'Hardest questions only — edge cases, exceptions, traps, multi-concept synthesis. Zero easy questions. Only what separates toppers from average students.',
        },
    },
    'vsq': {
        'name': 'Very Short Answer',
        'instruction': (
            'Each question requires a precise answer in MAXIMUM 2 sentences. '
            'Answer must be direct and to the point — no padding, no extra words. '
            'If answer needs only 1 sentence, keep it 1 sentence. '
            'STRICT LIMIT: 2 sentences maximum, no exceptions.'
        ),
        'answer_note': 'STRICT: maximum 2 sentences, direct and precise',
        'difficulty_rules': {
            'beginner': 'Direct recall only — facts, definitions, simple identification. Anyone who read the content once can answer. Zero analysis or inference.',
            'advance': 'Important exam-level questions — understanding and application based. How/why/compare type. Focus on high-weightage concepts serious students must know.',
            'expert': 'Hardest questions only — edge cases, exceptions, traps, multi-concept synthesis. Zero easy questions. Only what separates toppers from average students.',
        },
    },
    'sq': {
        'name': 'Short Answer',
        'instruction': (
            'Each question requires a well-structured answer between 5-8 sentences. '
            'Structure: Point → Explanation → Example/Evidence → Conclusion. '
            'Cover the concept properly — do not cut short. '
            'MINIMUM 5 sentences, MAXIMUM 8 sentences. '
            'If the question demands depth, use all 8 sentences.'
        ),
        'answer_note': 'STRICT: 5 to 8 sentences, structured with point-explanation-example-conclusion',
        'difficulty_rules': {
            'beginner': 'Direct recall only — facts, definitions, simple identification. Anyone who read the content once can answer. Zero analysis or inference.',
            'advance': 'Important exam-level questions — understanding and application based. How/why/compare type. Focus on high-weightage concepts serious students must know.',
            'expert': 'Hardest questions only — edge cases, exceptions, traps, multi-concept synthesis. Zero easy questions. Only what separates toppers from average students.',
        },
    },
    'lq': {
        'name': 'Long Answer / Essay',
        'instruction': (
            'Each question requires a detailed essay-style answer between 15-20 sentences. '
            'Structure: Introduction (2-3 sentences) → Main Body with multiple points (10-14 sentences) → Conclusion (2-3 sentences). '
            'Cover ALL aspects — mechanisms, examples, comparisons, real-world applications, limitations. '
            'MINIMUM 15 sentences, MAXIMUM 20 sentences. '
            'Each point must be fully explained — never leave a concept half-explained. '
            'This should read like a textbook answer — complete and professional.'
        ),
        'answer_note': 'STRICT: 15 to 20 sentences, full essay structure with introduction, detailed body, and conclusion',
        'difficulty_rules': {
            'beginner': 'Direct recall only — facts, definitions, simple identification. Anyone who read the content once can answer. Zero analysis or inference.',
            'advance': 'Important exam-level questions — understanding and application based. How/why/compare type. Focus on high-weightage concepts serious students must know.',
            'expert': 'Hardest questions only — edge cases, exceptions, traps, multi-concept synthesis. Zero easy questions. Only what separates toppers from average students.',
        },
    },
}

DIFFICULTY_SYSTEM = {
    'beginner': """━━━ DIFFICULTY: BEGINNER — STRICT ━━━
ONLY these types of questions allowed:
✓ Direct definitions — "What is X?"
✓ Simple identification — "Which of these is X?"
✓ Basic recall — directly stated in content
✓ Fill simple facts — names, dates, one-word answers

STRICTLY BANNED at beginner level:
✗ Why/How questions
✗ Comparison questions  
✗ Any analysis or inference
✗ Edge cases or exceptions
✗ Multi-concept questions

SELF CHECK before writing each question:
→ Can a student answer this by reading the content once? YES = allowed, NO = reject it""",

    'advance': """━━━ DIFFICULTY: ADVANCE — STRICT ━━━
These question types are REQUIRED:
✓ How/Why questions — explain mechanism or reason
✓ Comparison — X vs Y, key differences
✓ Application — in which real situation does X apply?
✓ Cause and effect — what leads to X, what results from X?
✓ Process questions — explain the steps of X

STRICTLY BANNED at advance level:
✗ Simple "What is X?" definition questions
✗ Questions answerable in one word
✗ Basic recall questions

SELF CHECK before writing each question:
→ Does this require understanding, not just memorization? YES = allowed, NO = reject it""",

    'expert': """━━━ DIFFICULTY: EXPERT — EXTREMELY STRICT ━━━
ONLY the hardest questions. Every single question must pass ALL these checks:

REQUIRED — each question must be ONE of these:
✓ TRAP — obvious answer is WRONG, correct answer is counterintuitive  
✓ EXCEPTION — "In which case does X NOT apply?"
✓ EDGE CASE — rare/unusual scenario that most people get wrong
✓ MISCONCEPTION — tests a commonly held false belief
✓ SYNTHESIS — must combine 2-3 concepts together to answer
✓ CRITICAL — limitation, failure condition, or flaw of X

ABSOLUTELY BANNED at expert level:
✗ Any definition question — "What is X?" = REJECTED
✗ Any question a beginner can answer
✗ Any question answerable by simple recall
✗ Obvious or straightforward questions
✗ Questions with obvious answers

MANDATORY SELF CHECK — ask yourself before each question:
→ Would a student who studied the topic get this wrong on first attempt? 
→ YES = good expert question
→ NO = too easy, REJECT IT and write harder one

TARGET: Only questions that appear in competitive exams, advanced tests, or interviews."""
}


# ─────────────────────────────────────────────────────────────
#  PROMPT BUILDER
# ─────────────────────────────────────────────────────────────
def build_question_prompt(text, num_questions, difficulty, language, question_type, domain):
    cfg = TYPE_CONFIGS[question_type]
    LANGUAGE_NAMES = {
        'english': 'English', 'hindi': 'Hindi', 'gujarati': 'Gujarati',
        'tamil': 'Tamil', 'telugu': 'Telugu', 'marathi': 'Marathi',
        'punjabi': 'Punjabi', 'bengali': 'Bengali', 'urdu': 'Urdu',
        'spanish': 'Spanish', 'arabic': 'Arabic', 'french': 'French',
        'portuguese': 'Portuguese', 'russian': 'Russian', 'indonesian': 'Indonesian',
        'japanese': 'Japanese', 'german': 'German', 'korean': 'Korean',
        'turkish': 'Turkish', 'vietnamese': 'Vietnamese', 'italian': 'Italian',
        'chinese': 'Mandarin Chinese', 'persian': 'Persian',
        'swahili': 'Swahili', 'dutch': 'Dutch',
    }
    lang = (
        "Auto-detect language from content and respond in that same language"
        if language == 'auto'
        else f"STRICTLY in {LANGUAGE_NAMES.get(language, language)} ONLY — every word, every option, every explanation must be in {LANGUAGE_NAMES.get(language, language)}. Do NOT mix with English."
    )

    diff_rule = cfg['difficulty_rules'].get(difficulty, cfg['difficulty_rules']['advance'])
    diff_system = DIFFICULTY_SYSTEM.get(difficulty, DIFFICULTY_SYSTEM['advance'])

    return f"""You are an expert educator. Your difficulty level is {difficulty.upper()}.

    ━━━ 100-ANGLE QUESTION COVERAGE — MANDATORY ━━━
Cover ALL these angles — never repeat same angle twice:

── FOUNDATION ──
1.  DEFINITION      — What is X exactly?
2.  FULL FORM       — What does the abbreviation stand for?
3.  ORIGIN          — When/who/how was X introduced?
4.  PURPOSE         — Why does X exist?
5.  IMPORTANCE      — Why is X significant?
6.  RULE            — What is the exact rule for X?
7.  FORMULA         — What is the formula or expression for X?
8.  COMPONENTS      — What parts make up X?
9.  TYPES           — What are the different types of X?
10. PROPERTIES      — What are the key characteristics of X?

── PROCESS ──
11. PROCESS         — How does X work step by step?
12. SEQUENCE        — What is the correct order of steps?
13. MECHANISM       — What is the internal mechanism behind X?
14. TRIGGER         — What starts or activates X?
15. CONDITION       — Under what condition does X apply?
16. TIMING          — When exactly does X happen?
17. FREQUENCY       — How often does X occur?
18. DURATION        — How long does X last?
19. SPEED           — How fast does X happen?
20. FLOW            — What is the direction or flow of X?

── PEOPLE & ROLES ──
21. WHO             — Who is responsible for X?
22. DECISION MAKER  — Who decides X?
23. ROLE            — What is the specific role in X?
24. RELATIONSHIP    — What is the relationship between A and B in X?
25. AUTHORITY       — Who has final say in X?
26. RESPONSIBILITY  — Whose fault when X goes wrong?
27. BENEFICIARY     — Who benefits from X?
28. AFFECTED PARTY  — Who is impacted when X happens?

── NUMBERS ──
29. NUMBER          — What is the specific number or limit in X?
30. MEASUREMENT     — What unit is used for X?
31. THRESHOLD       — What is the minimum or maximum for X?
32. RANGE           — What is the acceptable range for X?
33. RATIO           — What ratio applies to X?
34. STATISTICS      — What are known data or stats about X?

── LOCATION & CONTEXT ──
35. WHERE           — Where does X take place?
36. ENVIRONMENT     — In what setting does X occur?
37. SCOPE           — What is the boundary of X?
38. JURISDICTION    — In which domain does X apply?
39. CONTEXT         — In what specific context is X relevant?

── COMPARISON ──
40. COMPARISON      — How is X different from Y?
41. SIMILARITY      — How is X similar to Y?
42. ADVANTAGE       — What is the strength of X?
43. DISADVANTAGE    — What is the weakness of X?
44. BETTER OPTION   — When is X better than Y?
45. RANKING         — How does X rank among similar concepts?
46. CONTRAST        — What is the complete opposite of X?
47. EVOLUTION       — How has X changed over time?

── CAUSE & EFFECT ──
48. CAUSE           — What causes X?
49. EFFECT          — What results from X?
50. CHAIN REACTION  — What series of events does X trigger?
51. ROOT CAUSE      — What is the deepest reason for X?
52. SIDE EFFECT     — What are unintended effects of X?
53. DOMINO EFFECT   — If X happens what else follows?
54. PREVENTION      — What prevents X?
55. SOLUTION        — How can X be fixed or avoided?

── EXCEPTIONS ──
56. EXCEPTION       — When does X NOT apply?
57. EDGE CASE       — What happens in a rare scenario of X?
58. SPECIAL CASE    — Where does X behave differently?
59. LIMITATION      — Where does X fail?
60. CONFLICT        — What happens when X conflicts with Y?
61. OVERRIDE        — What overrides X?
62. LOOPHOLE        — Is there any gap in rule X?

── MISCONCEPTIONS ──
63. MISCONCEPTION   — What do people misunderstand about X?
64. COMMON MISTAKE  — What is the most frequent error about X?
65. TRAP            — What seems correct but is actually wrong about X?
66. MYTH            — What is a false belief about X?
67. CONFUSION       — What is often confused with X?
68. ASSUMPTION      — What wrong assumption do people make about X?

── PRACTICAL & REAL WORLD ──
69. REAL SCENARIO   — [Describe a real situation] what happens with X here?
70. APPLY THE RULE  — Given this situation [scenario] what is the correct outcome?
71. SPOT THE ERROR  — Here is a situation with a mistake — what went wrong?
72. CASE STUDY      — In this real example [give example] how does X apply?
73. FIELD EXAMPLE   — Give a specific real-world instance where X was seen
74. PLAYER ROLE     — In this scenario [describe] who does what regarding X?
75. DECISION MAKING — In this situation [describe] what decision is correct per X?
76. PROBLEM SOLVING — [Give a problem] how do you solve it using X?
77. IMPLEMENTATION  — How would you apply X in the real world?
78. INDUSTRY USE    — In which industry is X most used and how?

── BRAIN & CRITICAL THINKING ──
79. WHICH IS CORRECT — Two statements given — which one is accurate?
80. TRUE OR TRAP    — This statement seems right — is it correct or flawed?
81. FILL THE GAP    — [Situation described] what is missing or comes next?
82. REVERSE THINK   — X happened — what must have been the condition before?
83. PREDICT         — If [condition changes] what will happen to X?
84. RANK ORDER      — Arrange these steps of X in correct order
85. ODD ONE OUT     — Which does NOT belong to X category and why?
86. BEST CHOICE     — Given two options which is better here and why?
87. CONNECT DOTS    — How are X and Y connected?
88. WHAT IF WRONG   — If rule X was not followed what specific problem occurs?
89. WHAT IF CHANGED — If one condition changed how would X be different?
90. DEFEND OR CHALLENGE — Do you agree with this statement about X? Why?

── SYNTHESIS & ADVANCED ──
91. MULTI-CONCEPT   — How do X Y and Z work together in this situation?
92. CROSS-DOMAIN    — How does X relate to a similar concept in another field?
93. PATTERN         — What pattern is visible in X over time?
94. INFERENCE       — Based on X what can be logically concluded?
95. ASSUMPTION CHECK — What must be true for X to work as described?
96. GENERALIZATION  — Can X apply broadly or is it limited to specific cases?
97. PRIORITY        — If X and Y conflict which takes priority and why?
98. TRADE-OFF       — What is sacrificed when X is chosen over Y?
99. FUTURE IMPACT   — How might X evolve or change in future?
100. ULTIMATE CHALLENGE — [Most complex scenario combining multiple aspects] what is the correct analysis?

RULES:
- Minimum 30 different angles per set
- Angles 69-100 MUST include a specific scenario in the question
- Never use same angle twice in one set
- Order: foundation first then process then practical then brain last
- Harder difficulty = more angles 79-100 must be used

    CRITICAL INSTRUCTION — READ BEFORE GENERATING ANYTHING:
    You are generating {difficulty.upper()} level questions.
    {"Easy questions are COMPLETELY FORBIDDEN. Every question must be genuinely hard." if difficulty == 'expert' else ""}
    {"Definition-type questions are FORBIDDEN. Require understanding and application." if difficulty == 'advance' else ""}
    {"Keep all questions simple, direct recall only." if difficulty == 'beginner' else ""}

    {diff_system}

━━━ DOMAIN: {domain.replace('_', ' ').upper()} ━━━
Generate questions that test domain-specific understanding, not just surface reading.

ANSWER LENGTH RULES — NON NEGOTIABLE:
- FITB: Create a sentence with a blank.
- VSQ: Maximum 2 sentences response.
- SQ: Between 5-8 sentences structured text response.
- LQ: Between 15-20 sentences deep textbook response.
Current type is: {question_type.upper()} — follow its rule strictly.

━━━ LANGUAGE ━━━
{lang}

━━━ EXPLANATION RULES ━━━
Every question MUST have an explanation (2-3 sentences):
- Line 1: Why the answer is correct — cite the concept directly
- Line 2: Common misconception or why a wrong answer seems tempting  
- Line 3: Key insight or principle to remember

━━━ CONTENT ━━━
{text[:5500]}

Generate {num_questions} questions now based strictly on the content provided."""


# ─────────────────────────────────────────────────────────────
#  MAIN GENERATION SERVICE (OPTIMIZED & STRUCTURAL)
# ─────────────────────────────────────────────────────────────
def generate_questions_from_text(
        text,
        num_questions=10,
        difficulty='advance',
        language='auto',
        question_type='fitb',
):
    domain = detect_domain(text)
    prompt = build_question_prompt(text, num_questions, difficulty, language, question_type, domain)

    system_instruction = f"""You are an expert {domain.replace('_', ' ')} educator.
    Your mission is to generate content-grounded {TYPE_CONFIGS[question_type]['name']} questions.
    You must output valid structured JSON matching the provided schema exactly."""

    try:
        # Naya SDK native Configuration Setup with Strict Schema Enforcement
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=QuestionSetSchema,
            temperature=0.2
        )

        response = call_with_retry(contents=prompt, config=config)

        raw = response.text.strip()
        if not raw:
            raise ValueError('AI returned empty response — please retry.')

        # Pydantic schema validation happens automatically on loading
        data = json.loads(raw)

    except Exception as e:
        raise ValueError(f"Gemini API Execution Error inside Question Service: {str(e)}")

    if 'questions' not in data or len(data['questions']) == 0:
        raise ValueError('No questions generated — please retry.')

    # Exact field mapping normalization matching Django database properties
    normalized_questions = []
    seen = set()

    for q in data['questions']:
        # Base keys guaranteed mapping
        question_text = q.get('question', '').strip()
        answer_text = q.get('answer', '').strip()
        wrong_opt = q.get('wrong_option', '').strip()
        expl = q.get('explanation', '').strip()

        # Deduplication check using the first 60 characters
        dup_key = question_text.lower()[:60]
        if dup_key not in seen and question_text:
            seen.add(dup_key)
            normalized_questions.append({
                'question': question_text,
                'answer': answer_text,
                'wrong_option': wrong_opt,
                'explanation': expl
            })

    # Strict question count slicing as requested by views
    data['questions'] = normalized_questions[:num_questions]
    return data
