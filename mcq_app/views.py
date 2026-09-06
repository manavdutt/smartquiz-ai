import time
from datetime import date
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout


def get_client_ip(request):
    """Real IP Address nikalne ke liye helper function."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


from datetime import timedelta
from django.utils import timezone


def seconds_until_midnight():
    now = timezone.localtime()  # ← Sirf ye 1 line change hui
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((midnight - now).total_seconds()))


def rate_limit_check(identifier, is_guest=False):
    now = time.time()
    daily_limit = 3 if is_guest else 10

    daily_key = f"rl_daily_{identifier}"
    daily = cache.get(daily_key)

    # Midnight pe reset hoga
    secs_left = seconds_until_midnight()
    midnight_reset_at = now + secs_left

    if daily is None:
        daily = {'count': 0, 'reset_at': midnight_reset_at}

    if daily['count'] >= daily_limit:
        if is_guest:
            return False, "FORCE_LOGIN", 0
        hours_left = max(1, round((daily['reset_at'] - now) / 3600, 1))
        return False, "Daily limit reached. Resets at midnight. " + str(round(hours_left, 1)) + " hours left.", 0

    daily['count'] += 1
    cache.set(daily_key, daily, secs_left)

    return True, "", daily_limit - daily['count']


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import (
    Quiz, Question, QuizAttempt,
    QuestionSet, GeneratedQuestion,
    UsedQuestion, UploadedFile,
)
from .gemini_service import generate_mcqs_from_text, generate_mcqs_from_image, extract_text_via_gemini_vision
from .extractors import extract_from_pdf, extract_from_youtube, extract_from_docx
from django.db.models import Sum
import hashlib
from django.http import JsonResponse, HttpResponse
from .question_service import generate_questions_from_text


# ─────────────────────────────────────────
#  HELPER — Topic Hash + Used Questions
# ─────────────────────────────────────────

def get_topic_hash(text):
    """Same topic ka unique ID — pehle se pooche questions track karne ke liye"""
    return hashlib.md5(text[:300].lower().strip().encode()).hexdigest()


def get_previous_questions(topic_hash):
    """Is topic pe pehle se pooche gaye questions ki list"""
    try:
        from .models import UsedQuestion
        return list(
            UsedQuestion.objects.filter(
                topic_hash=topic_hash
            ).values_list('question_text', flat=True).order_by('-created_at')[:50]
        )
    except Exception:
        return []


def save_used_questions(questions_data, topic_hash):
    """Naye questions DB mein save karo — future mein repeat na ho"""
    try:
        from .models import UsedQuestion
        for q in questions_data:
            UsedQuestion.objects.get_or_create(
                question_text=q['question'],
                topic_hash=topic_hash
            )
    except Exception:
        pass


# ─────────────────────────────────────────
#  HOME (MCQ Generator for Quiz)
# ─────────────────────────────────────────
def home(request):
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # NAYI — teeno jagah same
        is_guest = not request.user.is_authenticated
        identifier = request.user.email if request.user.is_authenticated else get_client_ip(request)
        allowed, err_msg, remaining = rate_limit_check(identifier, is_guest=is_guest)

        if not allowed:
            if err_msg == "FORCE_LOGIN":
                if is_ajax:
                    return JsonResponse({
                        'error': 'You have used your 3 free generations. Please sign in with Google to continue.',
                        'force_login': True,
                        'login_url': '/accounts/google/login/'
                    }, status=403)
                return redirect('/accounts/google/login/')
            if is_ajax:
                return JsonResponse({'error': err_msg}, status=429)
            return redirect('home')

        input_type = request.POST.get('input_type', 'file')
        num_questions = int(request.POST.get('count', 5))
        difficulty = request.POST.get('difficulty', 'advance')
        language = request.POST.get('language', 'auto')

        try:
            mcq_data = None
            text = ""

            if input_type == 'file':
                uploaded_file = request.FILES.get('syllabus_file')
                if not uploaded_file:
                    if is_ajax:
                        return JsonResponse({'error': 'Please select a file to continue.'}, status=400)
                    messages.error(request, "No file selected!")
                    return redirect('home')

                content_type = uploaded_file.content_type
                file_name = uploaded_file.name.lower()

                if 'image' in content_type:
                    topic_hash = hashlib.md5(
                        f"{uploaded_file.name}_{uploaded_file.size}".encode()
                    ).hexdigest()
                    previous_questions = get_previous_questions(topic_hash)
                    mcq_data = generate_mcqs_from_image(
                        uploaded_file, num_questions, difficulty, language,
                        previous_questions=previous_questions
                    )
                    save_used_questions(mcq_data['questions'], topic_hash)

                elif 'pdf' in content_type or file_name.endswith('.pdf'):
                    text = extract_from_pdf(uploaded_file)
                    if not text:
                        if is_ajax:
                            return JsonResponse({'error': 'Could not extract text from this PDF. Make sure it is a text-based PDF, not a scanned image.'}, status=400)
                        messages.error(request, "Could not extract text from PDF!")
                        return redirect('home')
                    topic_hash = get_topic_hash(text)
                    previous_questions = get_previous_questions(topic_hash)
                    mcq_data = generate_mcqs_from_text(
                        text, num_questions, difficulty, language,
                        previous_questions=previous_questions
                    )
                    save_used_questions(mcq_data['questions'], topic_hash)

                # ── WORD FILE (.DOCX) SUPPORT ──
                elif 'wordprocessingml' in content_type or file_name.endswith(('.docx', '.doc')):
                    try:
                        text = extract_from_docx(uploaded_file)
                    except Exception as e:
                        if is_ajax:
                            return JsonResponse({'error': f'Could not read Word file: {str(e)}'}, status=400)
                        messages.error(request, f"Word file read failed: {str(e)}")
                        return redirect('home')

                    if not text:
                        if is_ajax:
                            return JsonResponse({'error': 'Word file is empty or has no readable text.'}, status=400)
                        messages.error(request, "Could not extract text from Word file!")
                        return redirect('home')

                    topic_hash = get_topic_hash(text)
                    previous_questions = get_previous_questions(topic_hash)
                    mcq_data = generate_mcqs_from_text(
                        text, num_questions, difficulty, language,
                        previous_questions=previous_questions
                    )
                    save_used_questions(mcq_data['questions'], topic_hash)

                else:
                    if is_ajax:
                        return JsonResponse({'error': 'Only PDF, Word (.docx), and image files are supported.'}, status=400)
                    messages.error(request, "Only PDF, Word, and Image files are supported!")
                    return redirect('home')

            elif input_type == 'text':
                text = request.POST.get('quiz_text', '').strip()
                if not text:
                    if is_ajax:
                        return JsonResponse({'error': 'Please paste some content before generating.'}, status=400)
                    messages.error(request, "Text field is empty!")
                    return redirect('home')
                topic_hash = get_topic_hash(text)
                previous_questions = get_previous_questions(topic_hash)
                mcq_data = generate_mcqs_from_text(
                    text, num_questions, difficulty, language,
                    previous_questions=previous_questions
                )
                save_used_questions(mcq_data['questions'], topic_hash)

            elif input_type == 'youtube':
                yt_url = request.POST.get('quiz_youtube', '').strip()
                if not yt_url:
                    if is_ajax:
                        return JsonResponse({'error': 'Please enter a valid YouTube URL.'}, status=400)
                    messages.error(request, "Please enter a YouTube URL!")
                    return redirect('home')
                text = extract_from_youtube(yt_url)
                topic_hash = get_topic_hash(text)
                previous_questions = get_previous_questions(topic_hash)
                mcq_data = generate_mcqs_from_text(
                    text, num_questions, difficulty, language,
                    previous_questions=previous_questions
                )
                save_used_questions(mcq_data['questions'], topic_hash)

            else:
                if is_ajax:
                    return JsonResponse({'error': 'Invalid input type selected.'}, status=400)
                messages.error(request, "Invalid input type!")
                return redirect('home')

            # ── DATABASE SAVE ──
            quiz = Quiz.objects.create(
                user=request.user if request.user.is_authenticated else None,
                title=mcq_data.get('title', 'MCQ Quiz'),
                input_type=input_type,
                difficulty=difficulty,
                language=language,
            )

            questions_to_save = mcq_data['questions'][:num_questions]

            for q in questions_to_save:
                Question.objects.create(
                    quiz=quiz,
                    question_text=q['question'],
                    option_a=q['options'].get('A', 'Option A Missing'),
                    option_b=q['options'].get('B', 'Option B Missing'),
                    option_c=q['options'].get('C', 'Option C Missing'),
                    option_d=q['options'].get('D', 'Option D Missing'),
                    correct_answer=q.get('correct_answer', 'A').upper(),
                    explanation=q.get('explanation', '')
                )

            # Uploaded file track karo
            try:
                if input_type == 'file' and uploaded_file:
                    uploaded_file.seek(0)
                    if 'image' in uploaded_file.content_type:
                        ftype = 'image'
                    elif 'pdf' in uploaded_file.content_type:
                        ftype = 'pdf'
                    else:
                        ftype = 'docx'
                    uf = UploadedFile(
                        user=request.user if request.user.is_authenticated else None,
                        original_filename=uploaded_file.name,
                        file_type=ftype,
                        file_size_bytes=uploaded_file.size,
                        generation_type='quiz',
                        quiz=quiz,
                    )
                    uf.file.save(uploaded_file.name, uploaded_file, save=True)
                elif input_type == 'youtube':
                    UploadedFile.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        original_filename=yt_url,
                        file_type='youtube',
                        file_size_bytes=0,
                        generation_type='quiz',
                        quiz=quiz,
                    )
                elif input_type == 'text':
                    UploadedFile.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        original_filename='Raw Text Input',
                        file_type='text',
                        file_size_bytes=len(text.encode('utf-8')),
                        generation_type='quiz',
                        quiz=quiz,
                    )
            except Exception:
                pass

            quiz_url = f'/quiz/{quiz.id}/'

            if is_ajax:
                return JsonResponse({'redirect_url': quiz_url})

            return redirect('quiz', quiz_id=quiz.id)

        except Exception as e:
            if is_ajax:
                return JsonResponse({'error': f'Something went wrong: {str(e)}. Please try again.'}, status=500)
            messages.error(request, f"Something went wrong: {str(e)}")
            return redirect('home')

    return render(request, 'mcq_app/home.html')


# ─────────────────────────────────────────
#  QUIZ VIEW
# ─────────────────────────────────────────
def quiz(request, quiz_id):
    quiz_obj = get_object_or_404(Quiz, id=quiz_id)
    if quiz_obj.user is not None and quiz_obj.user != request.user:
        return redirect('index')
    questions = quiz_obj.questions.all()

    if request.method == 'POST':
        score = 0
        total = questions.count()
        user_answers = {}

        for question in questions:
            selected = request.POST.get(f'question_{question.id}', '').upper()
            user_answers[str(question.id)] = selected
            if selected == question.correct_answer.upper():
                score += 1

        attempt = QuizAttempt.objects.create(
            quiz=quiz_obj,
            score=score,
            total_questions=total,
            user_answers=user_answers,
        )

        return redirect('result', attempt_id=attempt.id)

    context = {
        'quiz': quiz_obj,
        'questions': questions,
        'total': questions.count(),
    }
    return render(request, 'mcq_app/quiz.html', context)


# ─────────────────────────────────────────
#  RESULT
# ─────────────────────────────────────────
def result(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    if attempt.quiz.user is not None and attempt.quiz.user != request.user:
        return redirect('index')
    questions = attempt.quiz.questions.all()

    percentage = round((attempt.score / attempt.total_questions * 100), 1) if attempt.total_questions > 0 else 0
    wrong = attempt.total_questions - attempt.score
    stroke_dashoffset = round(251.2 - (251.2 * percentage / 100), 1)

    if percentage >= 80:
        performance = "Excellent! You Nailed It. 🎉"
    elif percentage >= 60:
        performance = "Great Job! You Passed. 👍"
    elif percentage >= 40:
        performance = "Keep Practicing! 📚"
    else:
        performance = "Don't Give Up! Try Again. 💪"

    questions_review = []
    for i, question in enumerate(questions, start=1):
        user_ans = attempt.user_answers.get(str(question.id), '')
        is_correct = user_ans == question.correct_answer.upper()

        answer_map = {
            'A': question.option_a,
            'B': question.option_b,
            'C': question.option_c,
            'D': question.option_d,
        }

        questions_review.append({
            'number': i,
            'question_text': question.question_text,
            'user_answer': user_ans,
            'user_answer_text': answer_map.get(user_ans, 'Not Answered'),
            'correct_answer': question.correct_answer,
            'correct_answer_text': answer_map.get(question.correct_answer, ''),
            'is_correct': is_correct,
            'explanation': question.explanation,
        })

    context = {
        'attempt': attempt,
        'percentage': percentage,
        'wrong': wrong,
        'stroke_dashoffset': stroke_dashoffset,
        'performance': performance,
        'questions_review': questions_review,
    }
    return render(request, 'mcq_app/result.html', context)


def index(request):
    return render(request, 'mcq_app/index.html')


# ─────────────────────────────────────────
#  QUESTION GENERATOR (Non-MCQ Types)
# ─────────────────────────────────────────
def question_generator(request):
    if request.method == 'GET':
        return render(request, 'mcq_app/questions.html')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    is_guest = not request.user.is_authenticated
    identifier = request.user.email if request.user.is_authenticated else get_client_ip(request)
    allowed, err_msg, remaining = rate_limit_check(identifier, is_guest=is_guest)

    if not allowed:
        if err_msg == "FORCE_LOGIN":
            if is_ajax:
                return JsonResponse({
                    'error': 'You have used your 3 free generations. Please sign in with Google to continue.',
                    'force_login': True,
                    'login_url': '/accounts/google/login/'
                }, status=403)
            return redirect('/accounts/google/login/')
        if is_ajax:
            return JsonResponse({'error': err_msg}, status=429)
        return redirect('question_generator')

    try:
        input_type = request.POST.get('input_type', 'text')
        question_type = request.POST.get('question_type', 'fitb')
        num_questions = int(request.POST.get('count', 10))
        difficulty = request.POST.get('difficulty', 'advance')
        language = request.POST.get('language', 'auto')

        text = ''

        if input_type == 'text':
            text = request.POST.get('quiz_text', '').strip()
            if not text:
                return JsonResponse({'error': 'Text field is empty. Please paste some content.'}, status=400)

        elif input_type == 'youtube':
            yt_url = request.POST.get('youtube_url', '').strip()
            if not yt_url:
                return JsonResponse({'error': 'Please enter a YouTube URL.'}, status=400)
            text = extract_from_youtube(yt_url)

        elif input_type == 'file':
            uploaded_file = request.FILES.get('quiz_file')
            if not uploaded_file:
                return JsonResponse({'error': 'No file was uploaded. Please select a file.'}, status=400)

            content_type = uploaded_file.content_type
            file_name = uploaded_file.name.lower()

            # ── PDF ──
            if 'pdf' in content_type or file_name.endswith('.pdf'):
                try:
                    text = extract_from_pdf(uploaded_file)
                except Exception as e:
                    return JsonResponse({'error': f'Could not read PDF: {str(e)}'}, status=400)

                if not text or len(text.strip()) < 20:
                    return JsonResponse({'error': 'No text found in this PDF. Please use a text-based PDF.'}, status=400)

            # ── WORD FILE (.DOCX) SUPPORT ──
            elif 'wordprocessingml' in content_type or file_name.endswith(('.docx', '.doc')):
                try:
                    text = extract_from_docx(uploaded_file)
                except Exception as e:
                    return JsonResponse({'error': f'Could not read Word file: {str(e)}'}, status=400)

                if not text or len(text.strip()) < 20:
                    return JsonResponse({'error': 'No text found in this Word file.'}, status=400)

            # ── IMAGE (ULTRA FAST WITH GEMINI VISION) ──
            elif 'image' in content_type or file_name.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                try:
                    text = extract_text_via_gemini_vision(uploaded_file)
                except Exception as e:
                    return JsonResponse({'error': f'Image processing failed: {str(e)}'}, status=400)

                if not text or len(text.strip()) < 5:
                    return JsonResponse({'error': f'Image can not find text .'}, status=400)

            else:
                return JsonResponse({'error': f'Unsupported file type: {content_type}. Please use PDF, DOCX, or an image.'}, status=400)

        # ── Call service ──
        result = generate_questions_from_text(
            text=text, num_questions=num_questions, difficulty=difficulty,
            language=language, question_type=question_type,
        )

        # ── Save to DB ──
        qset = QuestionSet.objects.create(
            user=request.user if request.user.is_authenticated else None,
            title=result.get('title', 'Question Set'), question_type=question_type,
            input_type=input_type, difficulty=difficulty, language=language,
        )

        for idx, q in enumerate(result.get('questions', []), start=1):  # Changed indexing to match new service response
            GeneratedQuestion.objects.create(
                question_set=qset, question_text=q.get('question', ''),
                answer=q.get('answer', ''), wrong_option=q.get('wrong_option', ''),
                explanation=q.get('explanation', ''), order=idx,
            )

        # Uploaded file track karo
        try:
            if input_type == 'file' and uploaded_file:
                uploaded_file.seek(0)
                if 'image' in uploaded_file.content_type:
                    ftype = 'image'
                elif 'pdf' in uploaded_file.content_type:
                    ftype = 'pdf'
                else:
                    ftype = 'docx'
                uf = UploadedFile(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename=uploaded_file.name,
                    file_type=ftype,
                    file_size_bytes=uploaded_file.size,
                    generation_type='question',
                    question_set=qset,
                )
                uf.file.save(uploaded_file.name, uploaded_file, save=True)
            elif input_type == 'youtube':
                UploadedFile.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename=yt_url,
                    file_type='youtube',
                    file_size_bytes=0,
                    generation_type='question',
                    question_set=qset,
                )
            elif input_type == 'text':
                UploadedFile.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename='Raw Text Input',
                    file_type='text',
                    file_size_bytes=len(text.encode('utf-8')),
                    generation_type='question',
                    question_set=qset,
                )
        except Exception:
            pass

        return JsonResponse({'redirect_url': f'/question-set/{qset.id}/'})

    except Exception as e:
        return JsonResponse({'error': f'Generation failed: {str(e)}'}, status=500)


def question_set_detail(request, set_id):
    from .models import QuestionSet, GeneratedQuestion
    qset = get_object_or_404(QuestionSet, id=set_id)
    if qset.user is not None and qset.user != request.user:
        return redirect('index')
    questions = qset.questions.all().order_by('order')
    return render(request, 'mcq_app/question_list.html', {'qset': qset, 'questions': questions})


def study_planner(request):
    if request.method == 'GET':
        import datetime
        return render(request, 'mcq_app/study_planner.html', {
            'today_date': datetime.date.today().isoformat()
        })

    try:
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        is_guest = not request.user.is_authenticated
        identifier = request.user.email if request.user.is_authenticated else get_client_ip(request)
        allowed, err_msg, remaining = rate_limit_check(identifier, is_guest=is_guest)

        if not allowed:
            if err_msg == "FORCE_LOGIN":
                if is_ajax:
                    return JsonResponse({
                        'error': 'You have used your 3 free generations. Please sign in with Google to continue.',
                        'force_login': True,
                        'login_url': '/accounts/google/login/'
                    }, status=403)
                return redirect('/accounts/google/login/')
            if is_ajax:
                return JsonResponse({'error': err_msg}, status=429)
            return redirect('home')

        # ── Form fields ──
        exam_date_str = request.POST.get('exam_date', '').strip()
        daily_hours = int(request.POST.get('daily_hours', 4))
        exam_format = request.POST.get('exam_format', 'mixed')
        target_score = request.POST.get('target_score', 'good')
        rest_days = int(request.POST.get('rest_days', 1))
        total_marks = int(request.POST.get('total_marks', 100))
        input_type = request.POST.get('input_type', 'file')
        language = request.POST.get('language', 'english')

        if not exam_date_str:
            return JsonResponse({'error': 'Please select an exam date.'}, status=400)

        from datetime import date
        try:
            exam_date = date.fromisoformat(exam_date_str)
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Please select a valid date.'}, status=400)

        if exam_date <= date.today():
            return JsonResponse({'error': 'Exam date must be in the future. Please select a future date.'}, status=400)

            # ── 1 week urgency rule ──         ← YE NAYA CODE YAHAN ADD KARO
        days_left_check = (exam_date - date.today()).days
        if days_left_check <= 7:
            target_val = request.POST.get('target_score', 'good')
            if target_val in ['good', 'excellent']:
                daily_hours = max(daily_hours, 4)
                rest_days = 0

        # ── Extract syllabus content ──
        syllabus_content = ''
        subject_name = ''

        if input_type == 'file':
            uploaded = request.FILES.get('syllabus_file')
            if uploaded:
                content_type = uploaded.content_type
                file_name = uploaded.name.lower()
                try:
                    if 'pdf' in content_type or file_name.endswith('.pdf'):
                        syllabus_content = extract_from_pdf(uploaded)
                    elif 'wordprocessingml' in content_type or file_name.endswith(('.docx', '.doc')):
                        syllabus_content = extract_from_docx(uploaded)
                    elif 'image' in content_type or file_name.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        syllabus_content = extract_text_via_gemini_vision(uploaded)
                    else:
                        return JsonResponse({'error': 'Unsupported file type. Use PDF, DOCX, or image.'}, status=400)
                except Exception as e:
                    return JsonResponse({'error': f'Could not read the uploaded file: {str(e)}'}, status=400)

                # Subject name — file name se guess karo
                subject_name = uploaded.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()

        elif input_type == 'text':
            syllabus_content = request.POST.get('syllabus_text', '').strip()
            if not syllabus_content:
                return JsonResponse({'error': 'Please upload a syllabus file or paste your topics.'}, status=400)
            # Pehli line se subject name guess karo
            subject_name = syllabus_content.split('\n')[0][:60].strip()

        elif input_type == 'youtube':
            yt_url = request.POST.get('quiz_youtube', '').strip()
            if not yt_url:
                return JsonResponse({'error': 'Please enter a YouTube URL.'}, status=400)
            try:
                syllabus_content = extract_from_youtube(yt_url)
                subject_name = 'YouTube Study Plan'
            except Exception as e:
                return JsonResponse({'error': f'YouTube transcript fetch failed: {str(e)}'}, status=400)

        if not syllabus_content:
            return JsonResponse({'error': 'Please upload a syllabus file or paste topics.'}, status=400)

        # ── AI se plan generate karo ──
        from .study_planner_service import generate_study_plan
        plan_data = generate_study_plan(
            syllabus_content=syllabus_content,
            exam_date=exam_date,
            daily_hours=daily_hours,
            exam_format=exam_format,
            target_score=target_score,
            rest_days=rest_days,
            total_marks=total_marks,
            subject_name=subject_name,
            language=language,
        )

        # ── DB mein save karo ──
        from .models import StudyPlan, StudyWeek, StudyDay, StudyTopic

        plan = StudyPlan.objects.create(
            user=request.user if request.user.is_authenticated else None,
            subject_name=subject_name,
            exam_date=exam_date,
            daily_hours=daily_hours,
            exam_format=exam_format,
            target_score=target_score,
            rest_days=rest_days,
            total_marks=total_marks,
            language=language,
            plan_title=plan_data.get('plan_title', f'{subject_name} Study Plan'),
            total_days=plan_data.get('total_days', 0),
            total_hours=plan_data.get('total_hours', 0),
            strategy_note=plan_data.get('strategy_note', ''),
            revision_tips=plan_data.get('revision_tips', []),
            important_topics=plan_data.get('important_topics', []),
        )

        # Week summaries
        for idx, week in enumerate(plan_data.get('week_summaries', []), start=1):
            StudyWeek.objects.create(
                plan=plan,
                week_number=week.get('week_number', idx),
                focus_area=week.get('focus_area', ''),
                total_hours=week.get('total_hours', 0),
                key_milestone=week.get('key_milestone', ''),
                order=idx,
            )

        # Daily plans
        for idx, day in enumerate(plan_data.get('daily_plans', []), start=1):
            day_obj = StudyDay.objects.create(
                plan=plan,
                day_number=day.get('day_number', idx),
                date_label=day.get('date_label', ''),
                is_rest_day=day.get('is_rest_day', False),
                daily_goal=day.get('daily_goal', ''),
                total_hours=day.get('total_hours', 0),
                order=idx,
            )
            for t_idx, topic in enumerate(day.get('topics', []), start=1):
                StudyTopic.objects.create(
                    day=day_obj,
                    topic=topic.get('topic', ''),
                    duration=topic.get('duration', 60),
                    priority=topic.get('priority', 'medium'),
                    difficulty=topic.get('difficulty', 'medium'),
                    description=topic.get('description', ''),
                    order=t_idx,
                )

            # Uploaded file track karo
        try:
            if input_type == 'file' and uploaded:
                uploaded.seek(0)
                if 'image' in uploaded.content_type:
                    ftype = 'image'
                elif 'pdf' in uploaded.content_type:
                    ftype = 'pdf'
                else:
                    ftype = 'docx'
                uf = UploadedFile(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename=uploaded.name,
                    file_type=ftype,
                    file_size_bytes=uploaded.size,
                    generation_type='plan',
                    study_plan=plan,
                )
                uf.file.save(uploaded.name, uploaded, save=True)
            elif input_type == 'youtube':
                UploadedFile.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename=yt_url,
                    file_type='youtube',
                    file_size_bytes=0,
                    generation_type='plan',
                    study_plan=plan,
                )
            elif input_type == 'text':
                UploadedFile.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    original_filename='Raw Text Input',
                    file_type='text',
                    file_size_bytes=len(syllabus_content.encode('utf-8')),
                    generation_type='plan',
                    study_plan=plan,
                )
        except Exception:
            pass

        return JsonResponse({'redirect_url': f'/study-plan/{plan.id}/'})

    except Exception as e:
        return JsonResponse({'error': f'Plan generation failed: {str(e)}'}, status=500)


def study_plan_detail(request, plan_id):
    from .models import StudyPlan
    plan = get_object_or_404(StudyPlan, id=plan_id)
    if plan.user is not None and plan.user != request.user:
        return redirect('index')
    weeks = plan.weeks.all()
    days = plan.days.prefetch_related('topics').all()

    # Stats
    total_topics = sum(day.topics.count() for day in days)
    rest_days_count = sum(1 for day in days if day.is_rest_day)
    study_days_count = sum(1 for day in days if not day.is_rest_day)

    days_left = (plan.exam_date - date.today()).days

    return render(request, 'mcq_app/study_plan_detail.html', {
        'plan': plan,
        'weeks': weeks,
        'days': days,
        'total_topics': total_topics,
        'rest_days_count': rest_days_count,
        'study_days_count': study_days_count,
        'days_left': max(days_left, 0),
        'today_date': date.today().isoformat(),
    })


def study_plans_list(request):
    from .models import Quiz, QuestionSet, StudyPlan
    if request.user.is_authenticated:
        quizzes = Quiz.objects.filter(user=request.user).order_by('-created_at')
        question_sets = QuestionSet.objects.filter(user=request.user).order_by('-created_at')
        plans = StudyPlan.objects.filter(user=request.user).order_by('-created_at')
    else:
        quizzes = Quiz.objects.none()
        question_sets = QuestionSet.objects.none()
        plans = StudyPlan.objects.none()
    return render(request, 'mcq_app/history.html', {
        'quizzes': quizzes,
        'question_sets': question_sets,
        'plans': plans,
    })


# ─────────────────────────────────────────────────────────────
#  STUDY PLAN PDF DOWNLOAD VIEW
#  views.py ke sabse neeche add karo
# ─────────────────────────────────────────────────────────────

def download_study_plan_pdf(request, plan_id):
    from .models import StudyPlan
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from io import BytesIO

    plan = get_object_or_404(StudyPlan, id=plan_id)
    if plan.user is not None and plan.user != request.user:
        return redirect('index')
    days = plan.days.prefetch_related('topics').all()
    weeks = plan.weeks.all()

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=plan.plan_title,
    )

    # ── COLORS ──
    INDIGO = colors.HexColor('#4f46e5')
    INDIGO_LIGHT = colors.HexColor('#e0e7ff')
    CYAN = colors.HexColor('#0891b2')
    EMERALD = colors.HexColor('#059669')
    AMBER = colors.HexColor('#d97706')
    ROSE = colors.HexColor('#e11d48')
    SLATE_900 = colors.HexColor('#0f172a')
    SLATE_700 = colors.HexColor('#334155')
    SLATE_500 = colors.HexColor('#64748b')
    SLATE_300 = colors.HexColor('#cbd5e1')
    SLATE_100 = colors.HexColor('#f1f5f9')
    WHITE = colors.white

    PRIORITY_COLORS = {
        'high': colors.HexColor('#fef2f2'),
        'medium': colors.HexColor('#fffbeb'),
        'low': colors.HexColor('#f0fdf4'),
    }
    PRIORITY_TEXT = {
        'high': colors.HexColor('#dc2626'),
        'medium': colors.HexColor('#d97706'),
        'low': colors.HexColor('#16a34a'),
    }
    DIFF_COLORS = {
        'hard': colors.HexColor('#f87171'),
        'medium': colors.HexColor('#fbbf24'),
        'easy': colors.HexColor('#4ade80'),
    }

    # ── STYLES ──
    styles = getSampleStyleSheet()

    def S(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    sTitle = S('sTitle',
               fontSize=22, fontName='Helvetica-Bold',
               textColor=SLATE_900, spaceAfter=4, leading=28)

    sSubtitle = S('sSubtitle',
                  fontSize=10, fontName='Helvetica',
                  textColor=SLATE_500, spaceAfter=2)

    sSection = S('sSection',
                 fontSize=11, fontName='Helvetica-Bold',
                 textColor=INDIGO, spaceBefore=14, spaceAfter=6,
                 borderPad=4)

    sBody = S('sBody',
              fontSize=9, fontName='Helvetica',
              textColor=SLATE_700, leading=14, spaceAfter=2)

    sSmall = S('sSmall',
               fontSize=8, fontName='Helvetica',
               textColor=SLATE_500, leading=11)

    sLabel = S('sLabel',
               fontSize=7.5, fontName='Helvetica-Bold',
               textColor=SLATE_500)

    sDayNum = S('sDayNum',
                fontSize=10, fontName='Helvetica-Bold',
                textColor=WHITE)

    sGoal = S('sGoal',
              fontSize=8.5, fontName='Helvetica-Oblique',
              textColor=SLATE_500, leading=12)

    sTopic = S('sTopic',
               fontSize=8.5, fontName='Helvetica-Bold',
               textColor=SLATE_700, leading=12)

    sTopicDesc = S('sTopicDesc',
                   fontSize=7.5, fontName='Helvetica',
                   textColor=SLATE_500, leading=10)

    sTip = S('sTip',
             fontSize=8.5, fontName='Helvetica',
             textColor=SLATE_700, leading=13)

    story = []

    # ═══════════════════════════════════════════
    # PAGE 1 — HEADER + STATS + OVERVIEW
    # ═══════════════════════════════════════════

    # Header block
    header_data = [[
        Paragraph(plan.plan_title or 'Study Plan', sTitle),
        ''
    ]]
    header_table = Table(header_data, colWidths=[130 * mm, 40 * mm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), INDIGO),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [INDIGO]),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))

    # Title row manually using table with colored background
    story.append(Table(
        [[Paragraph(f'<font color="white"><b>{plan.plan_title or "Study Plan"}</b></font>', S('th', fontSize=18, fontName='Helvetica-Bold', textColor=WHITE, leading=24))]],
        colWidths=[174 * mm],
        style=[
            ('BACKGROUND', (0, 0), (-1, -1), INDIGO),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ]
    ))

    # Sub-info row
    story.append(Table(
        [[
            Paragraph(f'<font color="#94a3b8">Exam Date:</font> <b>{plan.exam_date.strftime("%d %B %Y")}</b>', S('si', fontSize=8.5, fontName='Helvetica', textColor=WHITE)),
            Paragraph(f'<font color="#94a3b8">Format:</font> <b>{plan.get_exam_format_display() if hasattr(plan, "get_exam_format_display") else plan.exam_format.upper()}</b>', S('si2', fontSize=8.5, fontName='Helvetica', textColor=WHITE)),
            Paragraph(f'<font color="#94a3b8">Target:</font> <b>{plan.target_score.upper()}</b>', S('si3', fontSize=8.5, fontName='Helvetica', textColor=WHITE)),
            Paragraph(f'<font color="#94a3b8">Marks:</font> <b>{plan.total_marks}</b>', S('si4', fontSize=8.5, fontName='Helvetica', textColor=WHITE)),
        ]],
        colWidths=[50 * mm, 45 * mm, 40 * mm, 39 * mm],
        style=[
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#3730a3')),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ]
    ))
    story.append(Spacer(1, 8 * mm))

    # ── STATS ROW ──
    study_days_count = sum(1 for d in days if not d.is_rest_day)
    rest_days_count = sum(1 for d in days if d.is_rest_day)

    stats = [
        ('Total Days', str(plan.total_days), INDIGO),
        ('Study Hours', f'{plan.total_hours:.0f}h', CYAN),
        ('Study Days', str(study_days_count), EMERALD),
        ('Hours / Day', f'{plan.daily_hours}h', AMBER),
    ]

    stat_cells = []
    for label, value, color in stats:
        stat_cells.append(Table(
            [[Paragraph(f'<font color="{color.hexval() if hasattr(color, "hexval") else "#4f46e5"}"><b>{value}</b></font>',
                        S('sv', fontSize=20, fontName='Helvetica-Bold', textColor=color, leading=24, alignment=TA_CENTER))],
             [Paragraph(label, S('sl', fontSize=7.5, fontName='Helvetica-Bold', textColor=SLATE_500, alignment=TA_CENTER))]],
            style=[
                ('BACKGROUND', (0, 0), (-1, -1), SLATE_100),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('ROUNDEDCORNERS', [4, 4, 4, 4]),
            ]
        ))

    story.append(Table(
        [stat_cells],
        colWidths=[42 * mm, 42 * mm, 42 * mm, 42 * mm],
        style=[
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
    ))
    story.append(Spacer(1, 6 * mm))

    # ── STRATEGY NOTE ──
    if plan.strategy_note:
        story.append(Table(
            [[
                Paragraph('AI Strategy', S('stl', fontSize=8, fontName='Helvetica-Bold', textColor=INDIGO)),
                Paragraph(plan.strategy_note, S('stn', fontSize=8.5, fontName='Helvetica-Oblique', textColor=SLATE_700, leading=13)),
            ]],
            colWidths=[22 * mm, 148 * mm],
            style=[
                ('BACKGROUND', (0, 0), (-1, -1), INDIGO_LIGHT),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        ))
        story.append(Spacer(1, 6 * mm))

    # ── IMPORTANT TOPICS + TIPS (side by side) ──
    story.append(Paragraph('MUST-COVER TOPICS', S('mct', fontSize=9, fontName='Helvetica-Bold', textColor=INDIGO, spaceAfter=4)))

    if plan.important_topics:
        topic_rows = []
        for i, t in enumerate(plan.important_topics):
            topic_rows.append([
                Paragraph(f'{i + 1}.', S('tn', fontSize=8.5, fontName='Helvetica-Bold', textColor=ROSE, alignment=TA_CENTER)),
                Paragraph(t, S('tt', fontSize=8.5, fontName='Helvetica', textColor=SLATE_700, leading=12)),
            ])
        story.append(Table(
            topic_rows,
            colWidths=[8 * mm, 162 * mm],
            style=[
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff1f2')),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#fff1f2'), colors.HexColor('#ffe4e6')]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        ))
    story.append(Spacer(1, 5 * mm))

    # ── WEEKLY OVERVIEW ──
    if weeks:
        story.append(Paragraph('WEEKLY OVERVIEW', S('wo', fontSize=9, fontName='Helvetica-Bold', textColor=INDIGO, spaceAfter=4)))
        week_rows = [[
            Paragraph('Week', S('wh', fontSize=8, fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER)),
            Paragraph('Focus Area', S('wh2', fontSize=8, fontName='Helvetica-Bold', textColor=WHITE)),
            Paragraph('Hours', S('wh3', fontSize=8, fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER)),
            Paragraph('Milestone', S('wh4', fontSize=8, fontName='Helvetica-Bold', textColor=WHITE)),
        ]]
        for week in weeks:
            week_rows.append([
                Paragraph(f'W{week.week_number}', S('wd', fontSize=8.5, fontName='Helvetica-Bold', textColor=INDIGO, alignment=TA_CENTER)),
                Paragraph(week.focus_area, S('wd2', fontSize=8, fontName='Helvetica', textColor=SLATE_700, leading=11)),
                Paragraph(f'{week.total_hours:.1f}h', S('wd3', fontSize=8.5, fontName='Helvetica-Bold', textColor=CYAN, alignment=TA_CENTER)),
                Paragraph(week.key_milestone, S('wd4', fontSize=8, fontName='Helvetica', textColor=SLATE_700, leading=11)),
            ])

        story.append(Table(
            week_rows,
            colWidths=[14 * mm, 60 * mm, 18 * mm, 82 * mm],
            style=[
                ('BACKGROUND', (0, 0), (-1, 0), INDIGO),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, SLATE_100]),
                ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.3, SLATE_300),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # PAGE 2+ — DAY BY DAY SCHEDULE
    # ═══════════════════════════════════════════

    story.append(Paragraph('DAY-BY-DAY STUDY SCHEDULE', S('dbt', fontSize=13, fontName='Helvetica-Bold', textColor=INDIGO, spaceAfter=8)))

    for day in days:
        day_content = []

        # Day header
        if day.is_rest_day:
            header_bg = colors.HexColor('#f1f5f9')
            num_bg = colors.HexColor('#94a3b8')
            label_txt = 'REST DAY'
            label_col = SLATE_500
        else:
            header_bg = colors.HexColor('#eef2ff')
            num_bg = INDIGO
            label_txt = f'{day.total_hours:.1f} hours  •  {day.topics.count()} topics'
            label_col = INDIGO

        day_header = Table(
            [[
                Table(
                    [[Paragraph(str(day.day_number), S('dn', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER))]],
                    colWidths=[8 * mm], rowHeights=[8 * mm],
                    style=[('BACKGROUND', (0, 0), (-1, -1), num_bg), ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]
                ),
                Paragraph(f'<b>{day.date_label}</b>   <font color="#94a3b8">{label_txt}</font>',
                          S('dh', fontSize=8.5, fontName='Helvetica', textColor=SLATE_700, leading=12)),
            ]],
            colWidths=[12 * mm, 158 * mm],
            style=[
                ('BACKGROUND', (0, 0), (-1, -1), header_bg),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
        day_content.append(day_header)

        if day.is_rest_day:
            day_content.append(Table(
                [[Paragraph('Rest & recharge. Light revision optional.', S('rr', fontSize=8, fontName='Helvetica-Oblique', textColor=SLATE_500))]],
                colWidths=[170 * mm],
                style=[('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('LEFTPADDING', (0, 0), (-1, -1), 14), ('BACKGROUND', (0, 0), (-1, -1), WHITE)]
            ))
        else:
            if day.daily_goal:
                day_content.append(Table(
                    [[Paragraph(f'Goal: {day.daily_goal}', S('dg', fontSize=8, fontName='Helvetica-Oblique', textColor=SLATE_500, leading=11))]],
                    colWidths=[170 * mm],
                    style=[('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('LEFTPADDING', (0, 0), (-1, -1), 14), ('BACKGROUND', (0, 0), (-1, -1), WHITE)]
                ))

            topic_rows = []
            for topic in day.topics.all():
                p_color = PRIORITY_TEXT.get(topic.priority, SLATE_500)
                d_color = DIFF_COLORS.get(topic.difficulty, SLATE_300)
                topic_rows.append([
                    Paragraph(topic.topic, S('tp', fontSize=8.5, fontName='Helvetica-Bold', textColor=SLATE_700, leading=12)),
                    Paragraph(f'<font color="{p_color.hexval() if hasattr(p_color, "hexval") else "#64748b"}">{topic.priority.upper()}</font>',
                              S('tpr', fontSize=7.5, fontName='Helvetica-Bold', textColor=p_color, alignment=TA_CENTER)),
                    Paragraph(topic.difficulty.upper(),
                              S('td', fontSize=7.5, fontName='Helvetica-Bold', textColor=d_color, alignment=TA_CENTER)),
                    Paragraph(f'{topic.duration}m', S('tdur', fontSize=8, fontName='Helvetica-Bold', textColor=INDIGO, alignment=TA_CENTER)),
                ])
                if topic.description:
                    topic_rows.append([
                        Paragraph(topic.description, S('tdesc', fontSize=7.5, fontName='Helvetica-Oblique', textColor=SLATE_500, leading=10)),
                        '', '', '',
                    ])

            if topic_rows:
                day_content.append(Table(
                    topic_rows,
                    colWidths=[110 * mm, 20 * mm, 20 * mm, 20 * mm],
                    style=[
                        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, colors.HexColor('#f8fafc')]),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                        ('LEFTPADDING', (0, 0), (-1, -1), 14),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                        ('LINEBELOW', (0, -1), (-1, -1), 0.5, SLATE_300),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]
                ))

        day_content.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(day_content))

    # ═══════════════════════════════════════════
    # LAST PAGE — REVISION TIPS
    # ═══════════════════════════════════════════
    if plan.revision_tips:
        story.append(PageBreak())
        story.append(Paragraph('REVISION & EXAM TIPS', S('rt', fontSize=13, fontName='Helvetica-Bold', textColor=INDIGO, spaceAfter=8)))

        tip_rows = []
        for i, tip in enumerate(plan.revision_tips, start=1):
            tip_rows.append([
                Paragraph(str(i), S('tnum', fontSize=10, fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER)),
                Paragraph(tip, S('tiptext', fontSize=9, fontName='Helvetica', textColor=SLATE_700, leading=14)),
            ])

        story.append(Table(
            tip_rows,
            colWidths=[10 * mm, 160 * mm],
            style=[
                ('BACKGROUND', (0, 0), (0, -1), AMBER),
                ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.HexColor('#fffbeb'), colors.HexColor('#fef3c7')]),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#fde68a')),
            ]
        ))

    # ── BUILD ──
    doc.build(story)
    buffer.seek(0)

    filename = f"study_plan_{plan.id}_{plan.exam_date}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─────────────────────────────────────────────────────────────
#  views.py ke SABSE NEECHE add karo — dono functions
# ─────────────────────────────────────────────────────────────
@login_required
def delete_study_plan(request, plan_id):
    """Study plan aur uska sara data delete karo."""
    from .models import StudyPlan
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)
    plan.delete()  # CASCADE — weeks, days, topics sab delete honge
    return JsonResponse({'success': True, 'redirect_url': '/plans/'})


@login_required
def update_exam_date(request, plan_id):
    """
    Exam date update karo + poora plan regenerate karo naye schedule ke saath.
    Existing topics se syllabus reconstruct kiya jaata hai — API mein syllabus
    dobara upload karne ki zaroorat nahi.
    """
    from .models import StudyPlan, StudyWeek, StudyDay, StudyTopic
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    plan = get_object_or_404(StudyPlan, id=plan_id, user=request.user)

    new_date_str = request.POST.get('exam_date', '').strip()
    if not new_date_str:
        return JsonResponse({'error': 'Please provide a new exam date.'}, status=400)

    from datetime import date
    try:
        new_date = date.fromisoformat(new_date_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Please try again.'}, status=400)

    if new_date <= date.today():
        return JsonResponse({'error': 'New exam date must be in the future.'}, status=400)

    # ── Step 1: Existing topics se syllabus reconstruct karo ──
    existing_days = plan.days.prefetch_related('topics').all()
    all_topic_names = []

    for day in existing_days:
        for topic in day.topics.all():
            if topic.topic and topic.topic not in all_topic_names:
                all_topic_names.append(topic.topic)

    # Important topics bhi include karo
    for t in plan.important_topics:
        if t not in all_topic_names:
            all_topic_names.append(t)

    if not all_topic_names:
        return JsonResponse({'error': 'No topics found in this plan. Cannot regenerate.'}, status=400)

    syllabus_reconstructed = f"""Subject: {plan.subject_name}
Exam Format: {plan.exam_format}
Target: {plan.target_score}

Topics to cover:
{chr(10).join(f'- {t}' for t in all_topic_names)}

Important Topics (High Priority):
{chr(10).join(f'- {t}' for t in plan.important_topics)}
"""

    # ── Step 2: AI se naya plan generate karo ──
    try:
        from .study_planner_service import generate_study_plan
        new_plan_data = generate_study_plan(
            syllabus_content=syllabus_reconstructed,
            exam_date=new_date,
            daily_hours=plan.daily_hours,
            exam_format=plan.exam_format,
            target_score=plan.target_score,
            rest_days=plan.rest_days,
            total_marks=plan.total_marks,
            subject_name=plan.subject_name,
            language=plan.language,
        )
    except Exception as e:
        print(f"[UPDATE DATE ERROR] Regeneration failed: {e}")
        return JsonResponse({'error': f'Failed to regenerate plan: {str(e)}'}, status=500)

    # ── Step 3: Purana data delete karo ──
    plan.weeks.all().delete()
    plan.days.all().delete()  # CASCADE → topics bhi delete honge

    # ── Step 4: Plan fields update karo ──
    plan.exam_date = new_date
    plan.plan_title = new_plan_data.get('plan_title', plan.plan_title)
    plan.total_days = new_plan_data.get('total_days', 0)
    plan.total_hours = new_plan_data.get('total_hours', 0)
    plan.strategy_note = new_plan_data.get('strategy_note', '')
    plan.revision_tips = new_plan_data.get('revision_tips', [])
    plan.important_topics = new_plan_data.get('important_topics', plan.important_topics)
    plan.save()

    # ── Step 5: Naya data save karo ──
    for idx, week in enumerate(new_plan_data.get('week_summaries', []), start=1):
        StudyWeek.objects.create(
            plan=plan,
            week_number=week.get('week_number', idx),
            focus_area=week.get('focus_area', ''),
            total_hours=week.get('total_hours', 0),
            key_milestone=week.get('key_milestone', ''),
            order=idx,
        )

    for idx, day in enumerate(new_plan_data.get('daily_plans', []), start=1):
        day_obj = StudyDay.objects.create(
            plan=plan,
            day_number=day.get('day_number', idx),
            date_label=day.get('date_label', ''),
            is_rest_day=day.get('is_rest_day', False),
            daily_goal=day.get('daily_goal', ''),
            total_hours=day.get('total_hours', 0),
            order=idx,
        )
        for t_idx, topic in enumerate(day.get('topics', []), start=1):
            StudyTopic.objects.create(
                day=day_obj,
                topic=topic.get('topic', ''),
                duration=topic.get('duration', 60),
                priority=topic.get('priority', 'medium'),
                difficulty=topic.get('difficulty', 'medium'),
                description=topic.get('description', ''),
                order=t_idx,
            )

    days_left = (new_date - date.today()).days

    return JsonResponse({
        'success': True,
        'new_date': new_date.strftime('%d %B %Y'),
        'days_left': days_left,
        'reload': True,  # Frontend ko page reload karna hai
    })


def get_remaining_attempts(request):
    """User ki remaining daily attempts return karo."""
    now = time.time()
    secs_left = seconds_until_midnight()
    midnight_reset_at = now + secs_left

    if not request.user.is_authenticated:
        return JsonResponse({
            'guest': True,
            'daily_remaining': 3,
            'daily_limit': 3,
            'daily_used': 0,
            'hours_until_reset': round(secs_left / 3600, 1),
            'message': 'Sign in for 10 daily attempts'
        })

    identifier = request.user.email
    daily_key = f"rl_daily_{identifier}"
    daily = cache.get(daily_key)

    if daily is None:
        daily = {'count': 0, 'reset_at': midnight_reset_at}

    daily_limit = 10
    daily_used = daily['count']
    daily_remaining = max(0, daily_limit - daily_used)
    hours_until_reset = max(0, round((daily['reset_at'] - now) / 3600, 1))

    return JsonResponse({
        'guest': False,
        'daily_remaining': daily_remaining,
        'daily_limit': daily_limit,
        'daily_used': daily_used,
        'hours_until_reset': hours_until_reset,
    })


def custom_logout(request):
    if request.method == 'POST':
        auth_logout(request)
        response = redirect('index')
        response.delete_cookie('sessionid')
        return response
    return redirect('index')
