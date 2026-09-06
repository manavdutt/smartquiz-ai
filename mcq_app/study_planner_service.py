import json
from datetime import date, timedelta
from typing import List
from pydantic import BaseModel, Field
from google.genai import types
from .ai_client import client, call_with_retry


# ─────────────────────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────────────────────

class TopicItem(BaseModel):
    topic: str = Field(description="Topic or chapter name from syllabus.")
    duration: int = Field(description="Study duration in minutes for this topic.")
    priority: str = Field(description="Priority: 'high', 'medium', or 'low'.")
    difficulty: str = Field(description="Difficulty: 'easy', 'medium', or 'hard'.")
    description: str = Field(default="", description="1-line focus note for this topic.")


class DayPlanItem(BaseModel):
    day_number: int = Field(description="Day number starting from 1.")
    date_label: str = Field(description="Date in DD/MM/YYYY format.")
    is_rest_day: bool = Field(default=False, description="True if this is a rest day.")
    topics: List[TopicItem] = Field(default=[], description="Topics to study. Empty for rest days.")
    daily_goal: str = Field(default="", description="Motivational one-line goal for the day.")
    total_hours: float = Field(default=0.0, description="Total hours for this day (sum of durations / 60).")


class WeekSummary(BaseModel):
    week_number: int = Field(description="Week number starting from 1.")
    focus_area: str = Field(description="Main topic area this week.")
    total_hours: float = Field(description="Total planned hours this week.")
    key_milestone: str = Field(description="Target milestone by end of this week.")


class StudyPlanSchema(BaseModel):
    plan_title: str = Field(description="Title for the study plan.")
    total_days: int = Field(description="Total days in plan.")
    total_hours: float = Field(description="Total study hours.")
    strategy_note: str = Field(description="2-3 sentence smart strategy for this student.")
    week_summaries: List[WeekSummary] = Field(description="Week-by-week overview.")
    daily_plans: List[DayPlanItem] = Field(description="Complete day-by-day schedule.")
    revision_tips: List[str] = Field(description="5-7 practical exam tips based on format.")
    important_topics: List[str] = Field(description="Top 5-8 must-cover topics by importance.")


# ─────────────────────────────────────────────────────────────
#  MAIN GENERATOR
# ─────────────────────────────────────────────────────────────

def generate_study_plan(
        syllabus_content: str,
        exam_date: date,
        daily_hours: int,
        exam_format: str,
        target_score: str,
        rest_days: int,
        total_marks: int,
        subject_name: str = "",
        language: str = "english",
) -> dict:
    today = date.today()
    days_left = max((exam_date - today).days, 1)

    # Calculate realistic study days
    rest_days_total = (days_left // 7) * rest_days
    study_days = days_left - rest_days_total
    total_hours_est = study_days * daily_hours

    format_labels = {
        'mcq': 'MCQ / Objective — focus on speed, accuracy, key concepts',
        'subjective': 'Subjective / Theory — focus on detailed writing, key points',
        'mixed': 'Mixed (MCQ + Subjective) — balance concept clarity and writing',
        'practical': 'Practical / Coding — daily hands-on practice sessions essential',
    }
    target_labels = {
        'pass': 'Just Pass — cover all basics, prioritize high-weightage topics only',
        'good': 'Good Score (75-85%) — thorough understanding + regular practice',
        'excellent': 'Top Ranker (90%+) — master every topic, zero weak areas',
    }

    # Build date labels
    date_labels = [
        (today + timedelta(days=i)).strftime("%d/%m/%Y")
        for i in range(days_left)
    ]

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
    lang_name = LANGUAGE_NAMES.get(language, 'English')
    lang_instruction = (
        f"STRICTLY in {lang_name} ONLY — every word, topic name, goal, tip, and description must be in {lang_name}. Do NOT mix with English."
        if language != 'english'
        else "English"
    )

    prompt = f"""You are an expert academic study planner and coach.

Create a complete, realistic, day-by-day study plan.

━━━ EXAM DETAILS ━━━
Subject / Exam   : {subject_name if subject_name else 'General Exam'}
Language         : {lang_instruction}
Total Marks      : {total_marks}
Exam Date        : {exam_date.strftime('%d %B %Y')}
Days Until Exam  : {days_left} days
Exam Format      : {format_labels.get(exam_format, exam_format)}
Target Goal      : {target_labels.get(target_score, target_score)}

━━━ STUDENT AVAILABILITY ━━━
Daily Study Hours : {daily_hours} hours/day
Rest Days/Week    : {rest_days} day(s) per week
Total Study Days  : ~{study_days} days
Total Study Hours : ~{total_hours_est} hours

━━━ SYLLABUS / TOPICS PROVIDED ━━━
{syllabus_content[:4000] if syllabus_content else "No syllabus uploaded. Generate a smart plan using subject name and exam format above."}

━━━ DATE SEQUENCE ━━━
Day 1 Start: {date_labels[0]}
All dates in order: {', '.join(date_labels)}

━━━ GENERATION RULES ━━━
1. daily_plans: One entry per day, Day 1 to Day {days_left}.
   - Use the exact dates from the date sequence above.
   - Distribute rest days evenly (roughly every {max(7 // max(rest_days, 1), 1)} days).
   - LAST 3-5 DAYS: Full revision + mock test practice (not new topics).
   - Hard/heavy topics: schedule in first 60% of days.
   - Each topic: specific name from syllabus, duration in minutes, priority, difficulty.
   - daily_goal: one motivational line matching that day's work.
   - total_hours: must not exceed {daily_hours} hours.

2. week_summaries: One per week with clear focus area and milestone.

3. revision_tips: 5-7 specific, actionable tips for {exam_format} format exam.

4. important_topics: Top 5-8 topics by exam weightage/importance.

5. strategy_note: Smart 2-3 sentence personalized advice for this student's situation.

Be specific, realistic, and motivating. No filler content.
"""

    config = types.GenerateContentConfig(
        system_instruction=(
            "You are a professional study planner. "
            "Generate a complete, realistic day-by-day study plan. "
            "Output must strictly match StudyPlanSchema. "
            "Use specific topic names from the syllabus. "
            "Be practical and achievable."
        ),
        response_mime_type="application/json",
        response_schema=StudyPlanSchema,
        temperature=0.2,
    )

    response = call_with_retry(contents=prompt, config=config)

    raw = response.text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise Exception(
            "Study plan generation failed — AI response was too large. "
            "Please try with a shorter syllabus or fewer topics."
        )
    return data
