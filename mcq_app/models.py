from django.db import models
from django.conf import settings
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
)
from django.core.exceptions import ValidationError


# ══════════════════════════════════════════════════════════════
#  CUSTOM VALIDATORS
# ══════════════════════════════════════════════════════════════

def validate_correct_answer(value):
    """Correct answer sirf A, B, C, ya D honi chahiye."""
    if value.upper() not in ['A', 'B', 'C', 'D']:
        raise ValidationError(
            f"'{value}' is not valid. Only A, B, C, or D are allowed."
        )


def validate_future_date(value):
    """Exam date aaj se pehle nahi ho sakti."""
    from datetime import date
    if value < date.today():
        raise ValidationError('Exam date must be in the future.')


# ══════════════════════════════════════════════════════════════
#  SHARED CHOICES  (TextChoices — Django best practice)
# ══════════════════════════════════════════════════════════════

class InputType(models.TextChoices):
    FILE = 'file', 'File'
    TEXT = 'text', 'Text'
    YOUTUBE = 'youtube', 'YouTube'


class DifficultyLevel(models.TextChoices):
    BEGINNER = 'beginner', 'Beginner'
    ADVANCE = 'advance', 'Advance'
    EXPERT = 'expert', 'Expert'


class QuestionType(models.TextChoices):
    FITB = 'fitb', 'Fill in the Blanks'
    TF = 'tf', 'True / False'
    VSQ = 'vsq', 'Very Short Questions'
    SQ = 'sq', 'Short Questions'
    LQ = 'lq', 'Long Questions'


# ══════════════════════════════════════════════════════════════
#  MCQ QUIZ
# ══════════════════════════════════════════════════════════════

class Quiz(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(
        max_length=255,
        validators=[MinLengthValidator(3)],
        verbose_name='Title',
    )
    input_type = models.CharField(
        max_length=20,
        choices=InputType.choices,
        verbose_name='Input Type',
    )
    difficulty = models.CharField(
        max_length=10,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.ADVANCE,  # BUG FIX: 'medium' → 'advance'
        verbose_name='Difficulty',
    )
    language = models.CharField(
        max_length=20,
        default='auto',
        verbose_name='Language',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Quiz'
        verbose_name_plural = 'Quizzes'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.difficulty.upper()}] {self.title}"

    @property
    def question_count(self):
        return self.questions.count()


# ══════════════════════════════════════════════════════════════
#  MCQ QUESTION
# ══════════════════════════════════════════════════════════════

class Question(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE,
        related_name='questions',
    )
    question_text = models.TextField(
        validators=[MinLengthValidator(5)],
        verbose_name='Question',
    )
    option_a = models.CharField(max_length=500, verbose_name='Option A')
    option_b = models.CharField(max_length=500, verbose_name='Option B')
    option_c = models.CharField(max_length=500, verbose_name='Option C')
    option_d = models.CharField(max_length=500, verbose_name='Option D')
    correct_answer = models.CharField(
        max_length=1,
        validators=[validate_correct_answer],
        verbose_name='Correct Answer',
    )
    explanation = models.TextField(blank=True, verbose_name='Explanation')

    class Meta:
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'

    def __str__(self):
        return self.question_text[:60]

    def clean(self):
        if self.correct_answer:
            self.correct_answer = self.correct_answer.upper()
        super().clean()

    def save(self, *args, **kwargs):
        # Hamesha uppercase mein save karo
        if self.correct_answer:
            self.correct_answer = self.correct_answer.upper()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def options_list(self):
        return [
            ('A', self.option_a),
            ('B', self.option_b),
            ('C', self.option_c),
            ('D', self.option_d),
        ]

    @property
    def correct_option_text(self):
        mapping = {
            'A': self.option_a,
            'B': self.option_b,
            'C': self.option_c,
            'D': self.option_d,
        }
        return mapping.get(self.correct_answer, '')


# ══════════════════════════════════════════════════════════════
#  QUIZ ATTEMPT
# ══════════════════════════════════════════════════════════════

class QuizAttempt(models.Model):
    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE,
        related_name='attempts',
    )
    score = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name='Score',
    )
    total_questions = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name='Total Questions',
    )
    user_answers = models.JSONField(default=dict)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Quiz Attempt'
        verbose_name_plural = 'Quiz Attempts'
        ordering = ['-attempted_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__lte=models.F('total_questions')),
                name='score_lte_total_questions',
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0),
                name='score_gte_zero',
            ),
        ]

    def clean(self):
        if self.score is not None and self.total_questions is not None:
            if self.score > self.total_questions:
                raise ValidationError('Score cannot exceed total questions.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quiz.title} — {self.score}/{self.total_questions}"

    @property
    def percentage(self):
        if self.total_questions == 0:
            return 0
        return round((self.score / self.total_questions) * 100, 1)


# ══════════════════════════════════════════════════════════════
#  USED QUESTION  (duplicate prevention)
# ══════════════════════════════════════════════════════════════

class UsedQuestion(models.Model):
    question_text = models.TextField(
        validators=[MinLengthValidator(5)],
    )
    topic_hash = models.CharField(
        max_length=64,
        db_index=True,
        validators=[MinLengthValidator(32)],
        verbose_name='Topic Hash (MD5)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Used Question'
        verbose_name_plural = 'Used Questions'
        # Same question same topic pe dobara save na ho
        unique_together = [['question_text', 'topic_hash']]

    def __str__(self):
        return self.question_text[:80]


# ══════════════════════════════════════════════════════════════
#  QUESTION SET  (non-MCQ types)
# ══════════════════════════════════════════════════════════════

class QuestionSet(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(
        max_length=255,
        validators=[MinLengthValidator(3)],
        verbose_name='Title',
    )
    question_type = models.CharField(
        max_length=10,
        choices=QuestionType.choices,
        verbose_name='Question Type',
    )
    input_type = models.CharField(
        max_length=20,
        choices=InputType.choices,
        verbose_name='Input Type',
    )
    difficulty = models.CharField(
        max_length=10,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.ADVANCE,
        verbose_name='Difficulty',
    )
    language = models.CharField(
        max_length=20,
        default='auto',
        verbose_name='Language',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Question Set'
        verbose_name_plural = 'Question Sets'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_question_type_display()} — {self.title}"

    @property
    def question_count(self):
        return self.questions.count()


# ══════════════════════════════════════════════════════════════
#  GENERATED QUESTION
# ══════════════════════════════════════════════════════════════

class GeneratedQuestion(models.Model):
    question_set = models.ForeignKey(
        QuestionSet, on_delete=models.CASCADE,
        related_name='questions',
    )
    question_text = models.TextField(
        validators=[MinLengthValidator(5)],
        verbose_name='Question',
    )
    answer = models.TextField(verbose_name='Answer')
    wrong_option = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='Wrong Option (T/F only)',
    )
    explanation = models.TextField(blank=True, verbose_name='Explanation')
    order = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Order',
    )

    class Meta:
        ordering = ['order']
        verbose_name = 'Generated Question'
        verbose_name_plural = 'Generated Questions'

    def __str__(self):
        return self.question_text[:80]


# ══════════════════════════════════════════════════════════════
#  STUDY PLAN
# ══════════════════════════════════════════════════════════════

class StudyPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    subject_name = models.CharField(
        max_length=200, blank=True,
        verbose_name='Subject Name',
    )
    exam_date = models.DateField(
        validators=[validate_future_date],
        verbose_name='Exam Date',
    )
    daily_hours = models.IntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        verbose_name='Daily Study Hours',
    )
    exam_format = models.CharField(
        max_length=50, default='mixed',
        verbose_name='Exam Format',
    )
    target_score = models.CharField(
        max_length=50, default='good',
        verbose_name='Target Score',
    )
    rest_days = models.IntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        verbose_name='Rest Days Per Week',
    )
    total_marks = models.IntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        verbose_name='Total Marks',
    )

    # AI generated fields
    plan_title = models.CharField(max_length=300, blank=True)
    total_days = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    total_hours = models.FloatField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    language = models.CharField(
        max_length=20,
        default='english',
        verbose_name='Language',
    )

    strategy_note = models.TextField(blank=True)
    revision_tips = models.JSONField(default=list)
    important_topics = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Study Plan'
        verbose_name_plural = 'Study Plans'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.plan_title or self.subject_name} — {self.exam_date}"

    @property
    def days_left(self):
        from datetime import date
        delta = self.exam_date - date.today()
        return max(delta.days, 0)

    @property
    def is_expired(self):
        from datetime import date
        return self.exam_date < date.today()


# ══════════════════════════════════════════════════════════════
#  STUDY WEEK
# ══════════════════════════════════════════════════════════════

class StudyWeek(models.Model):
    plan = models.ForeignKey(
        StudyPlan, on_delete=models.CASCADE,
        related_name='weeks',
    )
    week_number = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name='Week Number',
    )
    focus_area = models.CharField(max_length=300, verbose_name='Focus Area')
    total_hours = models.FloatField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Total Hours',
    )
    key_milestone = models.CharField(max_length=500, verbose_name='Key Milestone')
    order = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ['order']
        verbose_name = 'Study Week'
        verbose_name_plural = 'Study Weeks'

    def __str__(self):
        return f"Week {self.week_number} — {self.focus_area}"


# ══════════════════════════════════════════════════════════════
#  STUDY DAY
# ══════════════════════════════════════════════════════════════

class StudyDay(models.Model):
    plan = models.ForeignKey(
        StudyPlan, on_delete=models.CASCADE,
        related_name='days',
    )
    day_number = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name='Day Number',
    )
    date_label = models.CharField(max_length=20, verbose_name='Date Label')
    is_rest_day = models.BooleanField(default=False, verbose_name='Rest Day?')
    daily_goal = models.CharField(max_length=500, blank=True, verbose_name='Daily Goal')
    total_hours = models.FloatField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Total Hours',
    )
    order = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ['order']
        verbose_name = 'Study Day'
        verbose_name_plural = 'Study Days'

    def __str__(self):
        label = 'REST' if self.is_rest_day else f'{self.total_hours}h'
        return f"Day {self.day_number} ({label}) — {self.date_label}"


# ══════════════════════════════════════════════════════════════
#  STUDY TOPIC
# ══════════════════════════════════════════════════════════════

class PriorityLevel(models.TextChoices):
    HIGH = 'high', 'High'
    MEDIUM = 'medium', 'Medium'
    LOW = 'low', 'Low'


class StudyTopic(models.Model):
    day = models.ForeignKey(
        StudyDay, on_delete=models.CASCADE,
        related_name='topics',
    )
    topic = models.CharField(
        max_length=300,
        validators=[MinLengthValidator(2)],
        verbose_name='Topic',
    )
    duration = models.IntegerField(
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(480)],
        verbose_name='Duration (minutes)',
    )
    priority = models.CharField(
        max_length=20,
        choices=PriorityLevel.choices,
        default=PriorityLevel.MEDIUM,
        verbose_name='Priority',
    )
    difficulty = models.CharField(
        max_length=20,
        default='medium',
        verbose_name='Difficulty',
    )
    description = models.CharField(
        max_length=500, blank=True,
        verbose_name='Description',
    )
    order = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ['order']
        verbose_name = 'Study Topic'
        verbose_name_plural = 'Study Topics'

    def __str__(self):
        return f"{self.topic} ({self.duration}min — {self.priority})"


# ══════════════════════════════════════════════════════════════
#  USER LOGIN LOG
# ══════════════════════════════════════════════════════════════

class UserLoginLog(models.Model):
    email = models.EmailField(verbose_name='Email', db_index=True)
    login_at = models.DateTimeField(null=True, blank=True, verbose_name='Login Time')
    logout_at = models.DateTimeField(null=True, blank=True, verbose_name='Logout Time')
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name='IP Address',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Currently Active?',
        help_text='True = currently logged in',
    )

    class Meta:
        verbose_name = 'User Login Log'
        verbose_name_plural = 'User Login Logs'
        ordering = ['-login_at']
        indexes = [
            models.Index(fields=['email', '-login_at']),
        ]

    def clean(self):
        if self.login_at and self.logout_at:
            if self.logout_at <= self.login_at:
                raise ValidationError('Logout time must be after login time.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        status = 'ACTIVE' if self.is_active else 'LOGGED OUT'
        return f"{self.email} [{status}] — {self.login_at}"

    @property
    def session_duration(self):
        """Session kitne minutes chala."""
        if self.login_at and self.logout_at:
            delta = self.logout_at - self.login_at
            return round(delta.total_seconds() / 60, 1)
        return None


# ══════════════════════════════════════════════════════════════
#  UPLOADED FILE TRACKER
# ══════════════════════════════════════════════════════════════

class UploadedFile(models.Model):
    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'Word (.docx)'),
        ('image', 'Image'),
        ('youtube', 'YouTube URL'),
        ('text', 'Raw Text'),
    ]

    GENERATION_CHOICES = [
        ('quiz', 'MCQ Quiz'),
        ('question', 'Question Set'),
        ('plan', 'Study Plan'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='User',
    )
    file = models.FileField(
        upload_to='uploads/%Y/%m/%d/',
        null=True, blank=True,
        verbose_name='File',
    )
    original_filename = models.CharField(
        max_length=255,
        verbose_name='Original Filename',
    )
    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPE_CHOICES,
        verbose_name='File Type',
    )
    file_size_bytes = models.PositiveIntegerField(
        default=0,
        verbose_name='File Size (bytes)',
    )
    generation_type = models.CharField(
        max_length=20,
        choices=GENERATION_CHOICES,
        verbose_name='Generation Type',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Link to generated content
    quiz = models.OneToOneField(
        'Quiz', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_file',
        verbose_name='Generated Quiz',
    )
    question_set = models.OneToOneField(
        'QuestionSet', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_file',
        verbose_name='Generated Questions',
    )
    study_plan = models.OneToOneField(
        'StudyPlan', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_file',
        verbose_name='Generated Plan',
    )

    class Meta:
        verbose_name = 'Uploaded File'
        verbose_name_plural = 'Uploaded Files'
        ordering = ['-uploaded_at']

    def __str__(self):
        user_str = self.user.email if self.user else 'Guest'
        return f"{self.original_filename} — {user_str} — {self.get_generation_type_display()}"

    @property
    def file_size_display(self):
        b = self.file_size_bytes
        if b > 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        elif b > 1024:
            return f"{b / 1024:.0f} KB"
        return f"{b} B"
