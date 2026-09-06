import json
import io
import PIL.Image
from google.genai import types
from .ai_client import client, call_with_retry, detect_domain

# ─────────────────────────────────────────────────────────────
#  DOMAIN QUESTION ANGLES (ORIGINAL UNTOUCHED)
# ─────────────────────────────────────────────────────────────
DOMAIN_ANGLES = {
    'coding': """CODING DOMAIN — Test these angles:
• SYNTAX: exact syntax, keywords, operators, symbols
• OUTPUT: "What will this code output?" — include real code snippets
• ERROR: "What is wrong with this code?" — debugging questions  
• COMPARISON: X vs Y (list vs tuple, == vs ===, TCP vs UDP)
• COMPLEXITY: Big O time/space analysis
• EDGE CASE: null/empty/negative input behavior
• BEST PRACTICE: which approach is better and why
• CONCEPT: when/why to use X over Y
MANDATORY: min 2 questions with actual code snippets, 1 output question, 1 error-detection question.""",

    'math_science': """MATH/SCIENCE DOMAIN — Test these angles:
• FORMULA: exact formula for X — and when it applies
• NUMERICAL: solve with actual numbers (include calculations)
• UNIT: SI units, conversions, dimensional analysis
• DERIVATION: how/why formula works
• APPLICATION: which formula applies in this scenario
• EXCEPTION: when does rule/formula NOT apply
• GRAPH: how X changes when Y changes (relationships)
• REAL WORLD: which phenomenon demonstrates this principle
MANDATORY: min 2 numerical/calculation questions, 1 exception-based question.""",

    'networking_cs': """NETWORKING/CS DOMAIN — Test these angles:
• LAYER: OSI/TCP layer functions, what happens at each layer
• PROTOCOL: which protocol handles X, port numbers, differences
• PROCESS: step-by-step what happens (3-way handshake, ARP, etc.)
• DEVICE: router vs switch vs hub vs bridge — exact differences
• ADDRESSING: IP classes, subnetting, MAC addressing
• ALGORITHM: routing algorithms, error detection methods
• NUMERICAL: bandwidth, latency, throughput calculations
• TROUBLESHOOTING: which layer is responsible for X problem
MANDATORY: min 1 process/sequence question, 1 comparison question, 1 numerical.""",

    'language_grammar': """LANGUAGE/GRAMMAR DOMAIN — Test these angles:
• RULE: grammar rule for X — exact rule with exceptions
• IDENTIFY: identify the X (part of speech, tense, device) in sentence
• ERROR: find the grammatical error in this sentence
• USAGE: when to use X vs Y (affect vs effect, who vs whom)
• CORRECT: which sentence is grammatically correct
• TRANSFORM: convert from X form to Y form
• LITERARY DEVICE: identify device used in given text
• MEANING: word/phrase meaning in given context
MANDATORY: min 2 sentence-based questions, 1 error-detection, 1 usage-comparison.""",

    'general_theory': """GENERAL THEORY DOMAIN — Test these angles:
• DEFINITION: precise definition — not just surface meaning
• CLASSIFICATION: which category/type does X belong to
• COMPARISON: key difference between X and Y concepts
• CAUSE-EFFECT: what causes X, what is the consequence of X
• SEQUENCE: correct order of steps in process X
• EXCEPTION: what is the exception to rule/principle X
• APPLICATION: in which real scenario would you apply X
• INFERENCE: based on content, what can be logically concluded
• CRITICAL: what is the limitation or weakness of X approach
MANDATORY: min 1 sequence question, 1 exception question, 1 application scenario.""",
}

# ─────────────────────────────────────────────────────────────
#  ANGLES 100 (ORIGINAL UNTOUCHED COMPLETE LIST)
# ─────────────────────────────────────────────────────────────
ANGLES_100 = """
── FOUNDATION ──
1.  DEFINITION       — What is X exactly?
2.  FULL FORM        — What does the abbreviation stand for?
3.  ORIGIN           — When/who/how was X introduced?
4.  PURPOSE          — Why does X exist?
5.  IMPORTANCE       — Why is X significant?
6.  RULE             — What is the exact rule for X?
7.  FORMULA          — What is the formula or expression for X?
8.  COMPONENTS       — What parts make up X?
9.  TYPES            — What are the different types of X?
10. PROPERTIES       — What are the key characteristics of X?

── PROCESS ──
11. PROCESS          — How does X work step by step?
12. SEQUENCE         — What is the correct order of steps?
13. MECHANISM        — What is the internal mechanism behind X?
14. TRIGGER          — What starts or activates X?
15. CONDITION        — Under what condition does X apply?
16. TIMING           — When exactly does X happen?
17. FREQUENCY        — How often does X occur?
18. DURATION         — How long does X last?
19. SPEED            — How fast does X happen?
20. FLOW             — What is the direction or flow of X?

── PEOPLE & ROLES ──
21. WHO              — Who is responsible for X?
22. DECISION MAKER   — Who decides X?
23. ROLE             — What is the specific role in X?
24. RELATIONSHIP     — What is the relationship between A and B in X?
25. AUTHORITY        — Who has final say in X?
26. RESPONSIBILITY   — Whose fault when X goes wrong?
27. BENEFICIARY      — Who benefits from X?
28. AFFECTED PARTY   — Who is impacted when X happens?

── NUMBERS ──
29. NUMBER           — What is the specific number or limit in X?
30. MEASUREMENT      — What unit is used for X?
31. THRESHOLD        — What is the minimum or maximum for X?
32. RANGE            — What is the acceptable range for X?
33. RATIO            — What ratio applies to X?
34. STATISTICS       — What are known data or stats about X?

── LOCATION & CONTEXT ──
35. WHERE            — Where does X take place?
36. ENVIRONMENT      — In what setting does X occur?
37. SCOPE            — What is the boundary of X?
38. JURISDICTION     — In which domain does X apply?
39. CONTEXT          — In what specific context is X relevant?

── COMPARISON ──
40. COMPARISON       — How is X different from Y?
41. SIMILARITY       — How is X similar to Y?
42. ADVANTAGE        — What is the strength of X?
43. DISADVANTAGE     — What is the weakness of X?
44. BETTER OPTION    — When is X better than Y?
45. RANKING          — How does X rank among similar concepts?
46. CONTRAST         — What is the complete opposite of X?
47. EVOLUTION        — How has X changed over time?

── CAUSE & EFFECT ──
48. CAUSE            — What causes X?
49. EFFECT           — What results from X?
50. CHAIN REACTION   — What series of events does X trigger?
51. ROOT CAUSE       — What is the deepest reason for X?
52. SIDE EFFECT      — What are unintended effects of X?
53. DOMINO EFFECT    — If X happens what else follows?
54. PREVENTION       — What prevents X?
55. SOLUTION         — How can X be fixed or avoided?

── EXCEPTIONS ──
56. EXCEPTION        — When does X NOT apply?
57. EDGE CASE        — What happens in a rare scenario of X?
58. SPECIAL CASE     — Where does X behave differently?
59. LIMITATION       — Where does X fail?
60. CONFLICT         — What happens when X conflicts with Y?
61. OVERRIDE         — What overrides X?
62. LOOPHOLE         — Is there any gap in rule X?

── MISCONCEPTIONS ──
63. MISCONCEPTION    — What do people misunderstand about X?
64. COMMON MISTAKE   — What is the most frequent error about X?
65. TRAP             — What seems correct but is actually wrong about X?
66. MYTH             — What is a false belief about X?
67. CONFUSION        — What is often confused with X?
68. ASSUMPTION       — What wrong assumption do people make about X?

── PRACTICAL & REAL WORLD ──
69. REAL SCENARIO    — Describe a real situation — what happens with X here?
70. APPLY THE RULE   — Given this situation [scenario] what is the correct outcome?
71. SPOT THE ERROR   — Here is a situation with a mistake — what went wrong?
72. CASE STUDY       — In this real example [give example] how does X apply?
73. FIELD EXAMPLE    — Give a specific real-world instance where X was seen
74. PLAYER ROLE      — In this scenario [describe] who does what regarding X?
75. DECISION MAKING  — In this situation [describe] what decision is correct per X?
76. PROBLEM SOLVING  — [Give a problem] how do you solve it using X?
77. IMPLEMENTATION   — How would you apply X in the real world?
78. INDUSTRY USE     — In which industry is X most used and how?

── BRAIN & CRITICAL THINKING ──
79. WHICH IS CORRECT — Two statements given — which one is accurate?
80. TRUE OR TRAP     — This statement seems right — is it correct or flawed?
81. FILL THE GAP     — [Situation described] what is missing or comes next?
82. REVERSE THINK    — X happened — what must have been the condition before?
83. PREDICT          — If [condition changes] what will happen to X?
84. RANK ORDER       — Arrange these steps of X in correct order
85. ODD ONE OUT      — Which does NOT belong to X category and why?
86. BEST CHOICE      — Given two options which is better here and why?
87. CONNECT DOTS     — How are X and Y connected?
88. WHAT IF WRONG    — If rule X was not followed what specific problem occurs?
89. WHAT IF CHANGED  — If one condition changed how would X be different?
90. DEFEND OR CHALLENGE — Do you agree with this statement about X? Why?

── SYNTHESIS & ADVANCED ──
91. MULTI-CONCEPT    — How do X Y and Z work together in this situation?
92. CROSS-DOMAIN     — How does X relate to a similar concept in another field?
93. PATTERN          — What pattern is visible in X over time?
94. INFERENCE        — Based on X what can be logically concluded?
95. ASSUMPTION CHECK — What must be true for X to work as described?
96. GENERALIZATION   — Can X apply broadly or is it limited to specific cases?
97. PRIORITY         — If X and Y conflict which takes priority and why?
98. TRADE-OFF        — What is sacrificed when X is chosen over Y?
99. FUTURE IMPACT    — How might X evolve or change in future?
100. ULTIMATE CHALLENGE — Most complex scenario combining multiple aspects — what is the correct analysis?
"""

# ─────────────────────────────────────────────────────────────
#  DIFFICULTY ENGINE (ORIGINAL UNTOUCHED)
# ─────────────────────────────────────────────────────────────
DIFFICULTY = {
    'beginner': """━━━ DIFFICULTY: BEGINNER — STRICT ━━━
ONLY these question types allowed:
✓ Direct definitions — "What is X?"
✓ Simple identification — "Which of these is X?"
✓ Basic recall — answer directly stated in content
✓ Simple facts — names, dates, one-word answers
✓ Options must be clearly distinct — easy to eliminate wrong ones

STRICTLY BANNED:
✗ Why/How questions
✗ Comparison or analysis questions
✗ Edge cases or exceptions
✗ Multi-concept questions
✗ Tricky or trap options
✗ Scenario-based questions

SELF CHECK before each question:
→ Can a first-time reader answer this by reading content once?
→ YES = allowed | NO = reject and write easier one""",

    'advance': """━━━ DIFFICULTY: ADVANCE — STRICT ━━━
REQUIRED question types:
✓ How/Why — explain mechanism or reason
✓ Comparison — X vs Y, key differences
✓ Application — in which situation does X apply?
✓ Cause and effect — what leads to X, what results from X?
✓ Process — explain the steps of X
✓ Options must be close — require careful thinking to pick correct one
✓ At least one option must be partially true but missing key detail

STRICTLY BANNED:
✗ Simple "What is X?" definition questions
✗ Questions answerable in one word
✗ Basic recall questions
✗ Obviously wrong options

SELF CHECK before each question:
→ Does this require understanding, not just memorization?
→ YES = allowed | NO = reject and write harder one""",

    'expert': """━━━ DIFFICULTY: EXPERT — EXTREMELY STRICT ━━━
Every single question MUST pass ALL these checks:

REQUIRED — each question must be one of:
✓ TRAP — obvious answer is WRONG, correct is counterintuitive
✓ EXCEPTION — "In which case does X NOT apply?"
✓ EDGE CASE — rare scenario that most people get wrong
✓ MISCONCEPTION — tests a commonly held false belief
✓ SYNTHESIS — must combine 2-3 concepts to answer correctly
✓ CRITICAL — limitation, failure condition, or flaw of X
✓ ALL 4 options must look correct to an average student
✓ Wrong options = real misconceptions + partial truths + plausible alternatives

ABSOLUTELY BANNED:
✗ Any definition question — "What is X?" = INSTANTLY REJECTED
✗ Any question a beginner can answer
✗ Simple recall questions
✗ Any obvious or straightforward question
✗ Options that are clearly wrong

SELF CHECK before each question:
→ Would a student who studied this topic get it wrong on first attempt?
→ YES = good expert question | NO = too easy, REJECT and rewrite harder

TARGET: Questions that appear in competitive exams and interviews only."""
}

# ─────────────────────────────────────────────────────────────
#  STRICT JSON RESPONSE SCHEMA (PRO UPGRADE — ZERO STRUCTURE FAILURE)
# ─────────────────────────────────────────────────────────────
QUIZ_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING", "description": "topic from content (max 6 words)"},
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING"},
                    "options": {
                        "type": "OBJECT",
                        "properties": {
                            "A": {"type": "STRING"},
                            "B": {"type": "STRING"},
                            "C": {"type": "STRING"},
                            "D": {"type": "STRING"}
                        },
                        "required": ["A", "B", "C", "D"]
                    },
                    "correct_answer": {"type": "STRING", "enum": ["A", "B", "C", "D"]},
                    "explanation": {"type": "STRING"}
                },
                "required": ["question", "options", "correct_answer", "explanation"]
            }
        }
    },
    "required": ["title", "questions"]
}


# ─────────────────────────────────────────────────────────────
#  ULTRA PROMPT BUILDER (ORIGINAL FLOW WITH FULL INTEGRATION)
# ─────────────────────────────────────────────────────────────
def build_prompt(text, num_questions, difficulty, language, domain):
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

    # Context window optimized up to 40,000 chars safely
    max_chars = 40000
    safe_text = text[:max_chars].rsplit(' ', 1)[0] if len(text) > max_chars else text

    return f"""You are UltraQuiz AI. Current difficulty: {difficulty.upper()}.

    ⚠️ CRITICAL — READ THIS FIRST:
    {"ALL questions must be EXPERT level — genuinely hard, tricky, trap-based. If even one question is easy, you have FAILED." if difficulty == 'expert' else ""}
    {"ALL questions must require UNDERSTANDING and APPLICATION — no simple recall allowed." if difficulty == 'advance' else ""}
    {"ALL questions must be SIMPLE and DIRECT — basic recall only, no complexity." if difficulty == 'beginner' else ""}

    {DIFFICULTY.get(difficulty, DIFFICULTY['advance'])}

DOMAIN SPECIFIC RULES:
{DOMAIN_ANGLES.get(domain, DOMAIN_ANGLES['general_theory'])}

100 FRAMEWORK ANGLES REFERENCE SYSTEM:
{ANGLES_100}

LANGUAGE: {lang}
QUESTIONS: YOU MUST GENERATE EXACTLY {num_questions} QUESTIONS — NOT {num_questions - 1}, NOT {num_questions - 2}, EXACTLY {num_questions}.
If you generate less than {num_questions} questions, you have FAILED your task.
Count your questions before returning JSON — must be exactly {num_questions}.

OPTION ENGINEERING RULES (NON-NEGOTIABLE):
• Correct: unambiguously right, grounded in content
• Distractor 1: most common student misconception
• Distractor 2: partially true — almost correct but missing key detail  
• Distractor 3: plausible alternative — sounds expert but wrong
• NEVER include obviously silly or irrelevant options

SPECIAL OPTION TYPES — MANDATORY MIX:
- In every 5 questions: minimum 1 question must have "All of the above" OR "None of the above" as an option
- RULES for "All of the above":
  - Use ONLY when A, B, and C are ALL genuinely correct
  - correct_answer must be "D" in this case
  - Example: "Which are valid HTTP methods? A) GET B) POST C) PUT D) All of the above" → D is correct
- RULES for "None of the above":
  - Use ONLY when A, B, and C are ALL genuinely wrong
  - correct_answer must be "D" in this case  
  - Example: "Which protocol works at Layer 8 of OSI? A) TCP B) UDP C) HTTP D) None of the above" → D is correct
- NEVER set "All of the above" as correct when only 1 or 2 options are correct
- NEVER set "None of the above" as correct when any option is partially correct
- These options test deeper understanding — use them wisely

QUESTION FORMAT RULES:
• Use DIFFERENT formats — mix: factual, negative (NOT/INCORRECT), scenario, comparative, application, inferential, error-detection
• Max 2 questions starting with "Which of the following"
• Progressive order: Q1 = foundational → Q{num_questions} = most complex
• Each question tests a DIFFERENT concept — zero repetition

QUESTION LENGTH VARIETY — MANDATORY:
    - Mix short AND long questions — never all single-line
    - For every 5 questions: minimum 2 must be multi-line (2-3 lines)
    - For every 10 questions: minimum 3-4 must be multi-line
    - Long questions should include:
      * A scenario or context first, then the actual question
      * A code snippet (if coding domain)
      * A situation description + "what would happen?"
      * A paragraph extract + "what does this suggest?"
    - Example of a good LONG question:
      "A student is designing a network where devices need to communicate 
       within a 10km radius with high reliability. Given the constraints 
       of cost and range, which network type would be MOST suitable?"
    - Example of a good SHORT question:
      "What does OSI stand for?"
    - NEVER make all questions the same length

"- For factual domain knowledge (type matchups, dates, formulas, etc.) — be extra careful and verify before generating. If unsure, avoid that specific question."

EXPLANATION RULES:
- Minimum 3 lines — no exceptions, never shorter
- Line 1: State clearly WHY the correct answer is right — reference the content directly, be specific
- Line 2: Explain WHY the most tempting wrong option is incorrect — what makes it misleading
- Line 3: Give the deeper concept, real-world context, or key insight a student must remember
- Use clear, professional language — no vague statements
- If the topic has a formula, process, or rule — mention it explicitly
- Make the student feel they genuinely learned something, not just got the answer
- Example of GOOD explanation:
  "The correct answer is B because TCP uses a 3-way handshake (SYN, SYN-ACK, ACK) to establish a reliable connection before data transfer begins.
   Option A is wrong because UDP does not establish any connection — it simply sends data without acknowledgment, making it faster but unreliable.
   The key distinction is that TCP guarantees delivery and order of packets, which is why it is used for web browsing and emails, while UDP is preferred for live streaming and gaming."

CONTENT:
{safe_text}

Generate {num_questions} expert-level questions now. Think before each question."""


# ─────────────────────────────────────────────────────────────
#  MAIN LOGIC ENGINES (PRO STRUCTURAL UPGRADE)
# ─────────────────────────────────────────────────────────────
def generate_mcqs_from_text(text, num_questions=5, difficulty='advance', language='auto', previous_questions=None):
    domain = detect_domain(text)
    prompt = build_prompt(text, num_questions, difficulty, language, domain)

    # ── PREVIOUS QUESTIONS BLOCK ──────────────────────────
    avoid_block = ""
    if previous_questions and len(previous_questions) > 0:
        prev_list = "\n".join([f"- {q}" for q in previous_questions[:50]])
        avoid_block = f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULE — NEVER REPEAT THESE QUESTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These questions have ALREADY been asked on this topic.
You MUST NOT repeat them OR ask from the same angle:

{prev_list}

You MUST approach the topic from COMPLETELY DIFFERENT angles.
Think: what has NOT been tested yet?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    full_prompt = prompt + avoid_block

    # PRO SYSTEM PERSONA SEPARATION
    system_instruction = f"""You are UltraQuiz AI — advanced MCQ engine.
    Domain: {domain.replace('_', ' ').upper()}
    Difficulty: {difficulty.upper()}
    YOUR PERSONALITY AT {difficulty.upper()} LEVEL:
    {"You are a STRICT examiner. Hard tricky questions only." if difficulty == 'expert' else ""}
    {"You are a SMART teacher. Understanding and application based questions." if difficulty == 'advance' else ""}
    {"You are a GENTLE teacher. Simple clear questions only." if difficulty == 'beginner' else ""}
    RULES: Never generic questions. Only content-based. Return complete valid JSON match structural schema."""

    try:
        # Structured Outputs Engine Integration
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=QUIZ_SCHEMA,
            temperature=0.3
        )

        response = call_with_retry(contents=full_prompt, config=config)

        raw = response.text.strip()
        data = json.loads(raw)

    except json.JSONDecodeError:
        raise ValueError("AI structure decoding failed — schema layout error.")
    except Exception as e:
        raise ValueError(f"Gemini API Execution Error: {str(e)}")

    if 'questions' not in data or len(data['questions']) == 0:
        raise ValueError("Questions could not be generated — please retry")

    # ── ALL OF ABOVE / NONE OF ABOVE VALIDATION ──────────────
    for q in data['questions']:
        options = q.get('options', {})
        q['options'] = options
        correct = str(q.get('correct_answer', '')).upper()

        if 'all of the above' in str(options.get('D', '')).lower():
            if correct != 'D':
                q['correct_answer'] = 'D'

        if 'none of the above' in str(options.get('D', '')).lower():
            if correct != 'D':
                q['correct_answer'] = 'D'

        for letter in ['A', 'B', 'C']:
            opt_text = str(options.get(letter, '')).lower()
            if 'all of the above' in opt_text or 'none of the above' in opt_text:
                options['D'] = options[letter]
                options[letter] = f"Option {letter} structural safety wrap"
                if correct == letter:
                    q['correct_answer'] = 'D'

    # ── Agar kam questions aaye to auto fallback logic ──
    if len(data['questions']) < num_questions:
        retry_prompt = full_prompt + f"\n\nCRITICAL: You only generated {len(data['questions'])} questions last time. You MUST generate exactly {num_questions} questions. Return all in complete schema JSON."
        try:
            retry_response = call_with_retry(contents=retry_prompt, config=config)
            retry_data = json.loads(retry_response.text.strip())
            if 'questions' in retry_data and len(retry_data['questions']) > len(data['questions']):
                data = retry_data
        except Exception:
            pass

    data['questions'] = data['questions'][:num_questions]
    return data


def generate_mcqs_from_image(image_file, num_questions=5, difficulty='advance', language='auto', previous_questions=None):
    # 1. Image ko safely open karo memory mein
    if isinstance(image_file, str):
        image = PIL.Image.open(image_file)
    else:
        image_bytes = image_file.read()
        image = PIL.Image.open(io.BytesIO(image_bytes))

    # 2. Kyunki hum image direct bhej rahe hain, hum domain ko 'general_theory' rakh sakte hain
    # ya Gemini khud image dekh kar domain decide kar lega.
    domain = 'general_theory'

    # Text ki jagah hum prompt ko bata rahe hain ki data image mein hai
    prompt = build_prompt("Analyze the attached image thoroughly to extract content.", num_questions, difficulty, language, domain)

    # ── PREVIOUS QUESTIONS BLOCK ──────────────────────────
    avoid_block = ""
    if previous_questions and len(previous_questions) > 0:
        prev_list = "\n".join([f"- {q}" for q in previous_questions[:50]])
        avoid_block = f"\n\nSTRICT RULE — NEVER REPEAT THESE QUESTIONS:\n{prev_list}"

    full_prompt = prompt + avoid_block

    # PRO SYSTEM PERSONA
    system_instruction = f"""You are UltraQuiz AI — advanced MCQ engine.
    Difficulty: {difficulty.upper()}
    RULES: Read the provided image carefully, extract the knowledge text from it, and generate the required MCQs based strictly on that text. Return valid JSON matching the schema."""

    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=QUIZ_SCHEMA,
            temperature=0.2
        )

        # 🚀 MAGIC LINE: Hum contents mein [image, full_prompt] dono ek sath bhej rahe hain!
        response = call_with_retry(contents=[image, full_prompt], config=config)

        raw = response.text.strip()
        data = json.loads(raw)

    except Exception as e:
        raise ValueError(f"Gemini Vision API Execution Error: {str(e)}")

    data['questions'] = data['questions'][:num_questions]
    return data


def extract_text_via_gemini_vision(image_file):
    """Gemini Vision ka use karke image se text 2 second mein extract karne ke liye"""

    if isinstance(image_file, str):
        image = PIL.Image.open(image_file)
    else:
        image_bytes = image_file.read()
        image_file.seek(0)  # Pointer reset for safety
        image = PIL.Image.open(io.BytesIO(image_bytes))

    response = call_with_retry(
        contents=[image, "Extract all readable text from this image accurately. Do not summarize, just give raw text."]
    )
    return response.text
