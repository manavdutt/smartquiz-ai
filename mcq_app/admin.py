from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.db.models import Count
from django.utils import timezone
from django.contrib.admin import AdminSite

from .models import (
    Quiz, Question, QuizAttempt, UsedQuestion,
    QuestionSet, GeneratedQuestion,
    StudyPlan, StudyWeek, StudyDay, StudyTopic,
    UserLoginLog, UploadedFile
)


# ══════════════════════════════════════════════════════════════
#  SHARED HELPERS
# ══════════════════════════════════════════════════════════════

def badge(text, color, icon=''):
    bg_color = f'{color}22'
    icon_str = f'{icon} ' if icon else ''
    return format_html(
        '<span style="background:{}; color:{}; padding:2px 10px; border-radius:20px; font-weight:700; font-size:11px;">{}</span>',
        bg_color, color, mark_safe(f'{icon_str}{text}')
    )


DIFFICULTY_COLORS = {
    'beginner': '#16a34a',
    'advance': '#f59e0b',
    'expert': '#ef4444',
    'easy': '#16a34a',  # ← ADD
    'medium': '#f59e0b',  # ← ADD
    'hard': '#ef4444',  # ← ADD
}

INPUT_ICONS = {
    'file': ('#f59e0b', '📄'),
    'text': ('#6366f1', '📝'),
    'youtube': ('#ef4444', '▶️'),
}


# ══════════════════════════════════════════════════════════════
#  INLINES
# ══════════════════════════════════════════════════════════════

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    show_change_link = True
    fieldsets = (
        (None, {
            'fields': ('question_text', 'correct_answer', 'explanation')
        }),
        ('Options', {
            'fields': ('option_a', 'option_b', 'option_c', 'option_d'),
            'classes': ('collapse',),
        }),
    )


class GeneratedQuestionInline(admin.StackedInline):
    model = GeneratedQuestion
    extra = 0
    show_change_link = True
    readonly_fields = ('order',)
    fields = ('order', 'question_text', 'answer', 'wrong_option', 'explanation')


class StudyWeekInline(admin.TabularInline):
    model = StudyWeek
    extra = 0
    show_change_link = True
    readonly_fields = ('week_number', 'focus_area', 'total_hours', 'key_milestone')
    fields = ('week_number', 'focus_area', 'total_hours', 'key_milestone')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class StudyDayInline(admin.TabularInline):
    model = StudyDay
    extra = 0
    show_change_link = True
    readonly_fields = ('day_number', 'date_label', 'is_rest_day', 'daily_goal', 'total_hours')
    fields = ('day_number', 'date_label', 'is_rest_day', 'total_hours', 'daily_goal')
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


class StudyTopicInline(admin.TabularInline):
    model = StudyTopic
    extra = 0
    show_change_link = True
    readonly_fields = ('order',)
    fields = ('order', 'topic', 'duration', 'priority', 'difficulty', 'description')


# ══════════════════════════════════════════════════════════════
#  QUIZ ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'user_display', 'input_type_badge', 'difficulty_badge',
        'language', 'question_count', 'attempt_count', 'created_at'
    )
    list_filter = ('input_type', 'difficulty', 'language', 'user', 'created_at')
    search_fields = ('title', 'user__email')
    readonly_fields = ('created_at',)
    inlines = [QuestionInline]
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('📋 Basic Information', {'fields': ('title', 'input_type', 'user')}),
        ('⚙️ Settings', {'fields': ('difficulty', 'language')}),
        ('🕐 Timestamps', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _question_count=Count('questions', distinct=True),
            _attempt_count=Count('attempts', distinct=True),
        )

    @admin.display(description='Questions', ordering='_question_count')
    def question_count(self, obj):
        c = obj._question_count
        return badge(c, '#4f46e5' if c > 0 else '#94a3b8')

    @admin.display(description='Attempts', ordering='_attempt_count')
    def attempt_count(self, obj):
        c = obj._attempt_count
        return badge(c, '#16a34a' if c > 0 else '#94a3b8')

    @admin.display(description='Input Type')
    def input_type_badge(self, obj):
        color, icon = INPUT_ICONS.get(obj.input_type, ('#94a3b8', '?'))
        return badge(obj.get_input_type_display(), color, icon)

    @admin.display(description='Difficulty')
    def difficulty_badge(self, obj):
        return badge(obj.difficulty.upper(), DIFFICULTY_COLORS.get(obj.difficulty, '#94a3b8'))

    @admin.display(description='Created By')
    def user_display(self, obj):
        if getattr(obj, 'user', None) and getattr(obj.user, 'email', None):
            return format_html(
                '<span style="color:#6366f1;font-weight:600;">👤 {}</span>',
                obj.user.email
            )
        return format_html(
            '<span style="color:#94a3b8;font-weight:500;">🌐 {}</span>',
            'Guest'
        )


# ══════════════════════════════════════════════════════════════
#  QUESTION ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('short_question_text', 'quiz_link', 'correct_answer_badge')
    list_filter = ('correct_answer', 'quiz__difficulty', 'quiz__input_type')
    search_fields = ('question_text', 'quiz__title')
    ordering = ('quiz', 'id')

    fieldsets = (
        ('🔗 Quiz Assignment', {'fields': ('quiz',)}),
        ('❓ Question Details', {'fields': ('question_text', 'correct_answer', 'explanation')}),
        ('🔤 Options', {'fields': ('option_a', 'option_b', 'option_c', 'option_d')}),
    )

    @admin.display(description='Question')
    def short_question_text(self, obj):
        text = obj.question_text[:80]
        if len(obj.question_text) > 80:
            text += '...'
        return format_html('<span style="font-weight:500;">{}</span>', text)

    @admin.display(description='Quiz')
    def quiz_link(self, obj):
        return format_html(
            '<span style="color:#6366f1;font-weight:600;">{}</span>',
            obj.quiz.title[:40]
        )

    @admin.display(description='Answer')
    def correct_answer_badge(self, obj):
        colors = {'A': '#6366f1', 'B': '#16a34a', 'C': '#f59e0b', 'D': '#ef4444'}
        answer = (obj.correct_answer or '').upper()
        color = colors.get(answer, '#94a3b8')
        return format_html(
            '<span style="background:{};color:white;padding:2px 12px;'
            'border-radius:20px;font-weight:700;font-size:12px;">{}</span>',
            color, answer or 'N/A'
        )


# ══════════════════════════════════════════════════════════════
#  QUIZ ATTEMPT ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('quiz_title', 'score_display', 'percentage_bar', 'performance_badge', 'attempted_at')
    list_filter = ('quiz__difficulty', 'attempted_at')
    search_fields = ('quiz__title',)
    readonly_fields = ('quiz', 'score', 'total_questions', 'user_answers', 'attempted_at')
    date_hierarchy = 'attempted_at'
    ordering = ('-attempted_at',)

    fieldsets = (
        ('📊 Attempt Info', {'fields': ('quiz', 'attempted_at')}),
        ('🏆 Results', {'fields': ('score', 'total_questions', 'user_answers')}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Quiz')
    def quiz_title(self, obj):
        return format_html(
            '<span style="font-weight:600;">{}</span>', obj.quiz.title[:50]
        )

    @admin.display(description='Score')
    def score_display(self, obj):
        return format_html(
            '<span style="font-weight:700;">{} / {}</span>',
            obj.score, obj.total_questions
        )

    @admin.display(description='Percentage')
    def percentage_bar(self, obj):
        pct = obj.percentage
        color = '#16a34a' if pct >= 70 else '#f59e0b' if pct >= 40 else '#ef4444'
        return format_html(
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<div style="width:100px;height:8px;background:#f1f5f9;border-radius:4px;overflow:hidden;">'
            '<div style="width:{}%;height:100%;background:{};border-radius:4px;"></div>'
            '</div>'
            '<span style="font-weight:700;color:{};font-size:12px;">{}%</span>'
            '</div>',
            pct, color, color, pct
        )

    @admin.display(description='Performance')
    def performance_badge(self, obj):
        pct = obj.percentage
        if pct >= 80:
            label, color = 'Excellent', '#16a34a'
        elif pct >= 60:
            label, color = 'Good', '#6366f1'
        elif pct >= 40:
            label, color = 'Average', '#f59e0b'
        else:
            label, color = 'Poor', '#ef4444'
        return badge(label, color)


# ══════════════════════════════════════════════════════════════
#  USED QUESTION ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(UsedQuestion)
class UsedQuestionAdmin(admin.ModelAdmin):
    list_display = ('short_question', 'topic_hash_badge', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('question_text', 'topic_hash')
    readonly_fields = ('question_text', 'topic_hash', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Question')
    def short_question(self, obj):
        text = obj.question_text[:80]
        if len(obj.question_text) > 80:
            text += '...'
        return format_html('<span style="font-weight:500;">{}</span>', text)

    @admin.display(description='Topic Hash')
    def topic_hash_badge(self, obj):
        return format_html(
            '<code style="background:#f1f5f9;color:#6366f1;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600;">{}</code>',
            obj.topic_hash[:12] + '...'
        )


# ══════════════════════════════════════════════════════════════
#  QUESTION SET ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(QuestionSet)
class QuestionSetAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'user_display', 'question_type_badge', 'input_type_badge',
        'difficulty_badge', 'language', 'question_count', 'created_at'
    )
    list_filter = ('question_type', 'input_type', 'difficulty', 'language', 'user', 'created_at')
    search_fields = ('title', 'user__email')
    readonly_fields = ('created_at',)
    inlines = [GeneratedQuestionInline]
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('📋 Basic Info', {'fields': ('title', 'question_type', 'input_type', 'user')}),
        ('⚙️ Settings', {'fields': ('difficulty', 'language')}),
        ('🕐 Timestamps', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _question_count=Count('questions', distinct=True)
        )

    @admin.display(description='Questions', ordering='_question_count')
    def question_count(self, obj):
        c = obj._question_count
        return badge(c, '#4f46e5' if c > 0 else '#94a3b8')

    @admin.display(description='Type')
    def question_type_badge(self, obj):
        icons = {
            'fitb': ('✏️', '#4f46e5'),
            'tf': ('✅', '#16a34a'),
            'vsq': ('⚡', '#0e7490'),
            'sq': ('📝', '#b45309'),
            'lq': ('📖', '#be185d'),
        }
        icon, color = icons.get(obj.question_type, ('❓', '#94a3b8'))
        display_text = obj.get_question_type_display() if hasattr(obj, 'get_question_type_display') else obj.question_type
        # FIX: Yahan icon parameter position sahi kar do
        return badge(display_text, color, icon)

    @admin.display(description='Input')
    def input_type_badge(self, obj):
        color, icon = INPUT_ICONS.get(obj.input_type, ('#94a3b8', '?'))
        return badge(obj.get_input_type_display(), color, icon)

    @admin.display(description='Difficulty')
    def difficulty_badge(self, obj):
        return badge(obj.difficulty.upper(), DIFFICULTY_COLORS.get(obj.difficulty, '#94a3b8'))

    @admin.display(description='Created By')
    def user_display(self, obj):
        if getattr(obj, 'user', None) and getattr(obj.user, 'email', None):
            return format_html(
                '<span style="color:#6366f1;font-weight:600;">👤 {}</span>',
                obj.user.email
            )
        return mark_safe(
            '<span style="color:#94a3b8;font-weight:500;">🌐 Guest</span>'
        )


# ══════════════════════════════════════════════════════════════
#  GENERATED QUESTION ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(GeneratedQuestion)
class GeneratedQuestionAdmin(admin.ModelAdmin):
    list_display = ('short_question', 'question_set_link', 'short_answer', 'order')
    list_filter = ('question_set__question_type', 'question_set__difficulty')
    search_fields = ('question_text', 'answer', 'question_set__title')
    readonly_fields = ('order',)
    ordering = ('question_set', 'order')

    fieldsets = (
        ('🔗 Set Assignment', {'fields': ('question_set', 'order')}),
        ('❓ Question', {'fields': ('question_text',)}),
        ('✅ Answer', {'fields': ('answer', 'wrong_option', 'explanation')}),
    )

    @admin.display(description='Question')
    def short_question(self, obj):
        text = obj.question_text[:75]
        if len(obj.question_text) > 75:
            text += '...'
        return format_html('<span style="font-weight:500;">{}</span>', text)

    @admin.display(description='Question Set')
    def question_set_link(self, obj):
        icons = {'fitb': '✏️', 'tf': '✅', 'vsq': '⚡', 'sq': '📝', 'lq': '📖'}
        icon = icons.get(obj.question_set.question_type, '?')
        return format_html(
            '<span style="color:#6366f1;font-weight:600;">{} {}</span>',
            icon, obj.question_set.title[:35]
        )

    @admin.display(description='Answer')
    def short_answer(self, obj):
        text = obj.answer[:50]
        if len(obj.answer) > 50:
            text += '...'
        return format_html(
            '<span style="color:#16a34a;font-weight:600;">{}</span>', text
        )


# ══════════════════════════════════════════════════════════════
#  STUDY PLAN ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = (
        'plan_title_display', 'user_display', 'subject_badge', 'exam_date',
        'days_left_badge', 'target_badge', 'daily_hours_badge',
        'total_days', 'created_at'
    )
    list_filter = ('target_score', 'exam_format', 'daily_hours', 'user', 'created_at')
    search_fields = ('plan_title', 'subject_name', 'user__email')
    readonly_fields = (
        'plan_title', 'total_days', 'total_hours',
        'strategy_note', 'revision_tips', 'important_topics', 'language', 'created_at'
    )
    inlines = [StudyWeekInline, StudyDayInline]
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('📚 Subject & Exam', {
            'fields': ('user', 'subject_name', 'exam_date', 'total_marks', 'exam_format', 'language')
        }),
        ('🎯 Goals', {
            'fields': ('target_score', 'daily_hours', 'rest_days')
        }),
        ('🤖 AI Generated', {
            'fields': ('plan_title', 'total_days', 'total_hours', 'strategy_note'),
        }),
        ('📋 Topics & Tips', {
            'fields': ('important_topics', 'revision_tips'),
            'classes': ('collapse',),
        }),
        ('🕐 Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description='Plan Title')
    def plan_title_display(self, obj):
        title = obj.plan_title or obj.subject_name or 'Untitled Plan'
        return format_html(
            '<span style="font-weight:700;color:#1e293b;">{}</span>',
            title[:45]
        )

    @admin.display(description='Created By')
    def user_display(self, obj):
        if getattr(obj, 'user', None) and getattr(obj.user, 'email', None):
            return format_html(
                '<span style="color:#6366f1;font-weight:600;">👤 {}</span>',
                obj.user.email
            )
        return format_html(
            '<span style="color:#94a3b8;font-weight:500;">🌐 Guest</span>'
        )

    @admin.display(description='Subject')
    def subject_badge(self, obj):
        name = obj.subject_name[:20] if obj.subject_name else 'N/A'
        return badge(name, '#6366f1', '📚')

    @admin.display(description='Days Left')
    def days_left_badge(self, obj):
        days = obj.days_left
        if obj.is_expired:
            return badge('Expired', '#ef4444', '⚠️')
        elif days <= 7:
            return badge(f'{days}d left', '#ef4444', '🔥')
        elif days <= 30:
            return badge(f'{days}d left', '#f59e0b', '⏳')
        else:
            return badge(f'{days}d left', '#16a34a', '✅')

    @admin.display(description='Target')
    def target_badge(self, obj):
        colors = {'pass': '#94a3b8', 'good': '#6366f1', 'excellent': '#16a34a'}
        icons = {'pass': '🎯', 'good': '💪', 'excellent': '🏆'}
        color = colors.get(obj.target_score, '#94a3b8')
        icon = icons.get(obj.target_score, '🎯')
        return badge(obj.target_score.upper(), color, icon)

    @admin.display(description='Daily Hours')
    def daily_hours_badge(self, obj):
        color = '#ef4444' if obj.daily_hours >= 8 else '#f59e0b' if obj.daily_hours >= 4 else '#16a34a'
        return badge(f'{obj.daily_hours}h/day', color, '⏰')


# ══════════════════════════════════════════════════════════════
#  STUDY DAY ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(StudyDay)
class StudyDayAdmin(admin.ModelAdmin):
    list_display = (
        'day_number', 'plan_link', 'date_label',
        'day_type_badge', 'total_hours', 'topic_count', 'daily_goal_short'
    )
    list_filter = ('is_rest_day', 'plan__target_score')
    search_fields = ('plan__plan_title', 'plan__subject_name', 'daily_goal')
    readonly_fields = ('day_number', 'date_label', 'plan', 'total_hours', 'order')
    inlines = [StudyTopicInline]
    ordering = ('plan', 'order')

    fieldsets = (
        ('📅 Day Info', {'fields': ('plan', 'day_number', 'date_label', 'is_rest_day')}),
        ('🎯 Goals', {'fields': ('daily_goal', 'total_hours')}),
    )

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _topic_count=Count('topics', distinct=True)
        )

    @admin.display(description='Plan')
    def plan_link(self, obj):
        title = obj.plan.plan_title or obj.plan.subject_name or 'Plan'
        return format_html(
            '<span style="color:#6366f1;font-weight:600;">{}</span>',
            title[:30]
        )

    @admin.display(description='Type')
    def day_type_badge(self, obj):
        if obj.is_rest_day:
            return badge('Rest Day', '#94a3b8', '😴')
        return badge('Study Day', '#6366f1', '📖')

    @admin.display(description='Topics', ordering='_topic_count')
    def topic_count(self, obj):
        c = obj._topic_count
        return badge(c, '#4f46e5' if c > 0 else '#94a3b8')

    @admin.display(description='Daily Goal')
    def daily_goal_short(self, obj):
        if not obj.daily_goal:
            return '—'
        text = obj.daily_goal[:50]
        if len(obj.daily_goal) > 50:
            text += '...'
        return format_html(
            '<span style="color:#475569;font-style:italic;">{}</span>', text
        )


# ══════════════════════════════════════════════════════════════
#  STUDY TOPIC ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(StudyTopic)
class StudyTopicAdmin(admin.ModelAdmin):
    list_display = (
        'topic', 'day_link', 'duration_badge',
        'priority_badge', 'difficulty_badge', 'order'
    )
    list_filter = ('priority', 'difficulty', 'day__plan__target_score')
    search_fields = ('topic', 'description', 'day__plan__subject_name')
    ordering = ('day__plan', 'day__order', 'order')

    fieldsets = (
        ('📅 Day Assignment', {'fields': ('day', 'order')}),
        ('📖 Topic Details', {'fields': ('topic', 'description')}),
        ('⚙️ Settings', {'fields': ('duration', 'priority', 'difficulty')}),
    )

    @admin.display(description='Day')
    def day_link(self, obj):
        return format_html(
            '<span style="color:#6366f1;font-weight:600;">Day {} — {}</span>',
            obj.day.day_number, obj.day.date_label
        )

    @admin.display(description='Duration')
    def duration_badge(self, obj):
        color = '#ef4444' if obj.duration >= 120 else '#f59e0b' if obj.duration >= 60 else '#16a34a'
        return badge(f'{obj.duration}min', color, '⏱️')

    @admin.display(description='Priority')
    def priority_badge(self, obj):
        colors = {'high': '#ef4444', 'medium': '#f59e0b', 'low': '#16a34a'}
        icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        color = colors.get(obj.priority, '#94a3b8')
        icon = icons.get(obj.priority, '')
        return badge(obj.priority.upper(), color, icon)

    @admin.display(description='Difficulty')
    def difficulty_badge(self, obj):
        return badge(obj.difficulty.upper(), DIFFICULTY_COLORS.get(obj.difficulty, '#94a3b8'))


# ══════════════════════════════════════════════════════════════
#  USER LOGIN LOG ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(UserLoginLog)
class UserLoginLogAdmin(admin.ModelAdmin):
    list_display = (
        'email', 'status_badge', 'login_at',
        'logout_at', 'session_duration_display', 'ip_address'
    )
    list_filter = ('is_active', 'login_at')
    search_fields = ('email', 'ip_address')
    readonly_fields = ('email', 'login_at', 'logout_at', 'ip_address', 'is_active')
    date_hierarchy = 'login_at'
    ordering = ('-login_at',)

    fieldsets = (
        ('👤 User', {'fields': ('email', 'ip_address')}),
        ('🕐 Session', {'fields': ('login_at', 'logout_at', 'is_active')}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Status')
    def status_badge(self, obj):
        if obj.is_active:
            return badge('Online', '#16a34a', '🟢')
        return badge('Offline', '#94a3b8')

    @admin.display(description='Session Duration')
    def session_duration_display(self, obj):
        mins = obj.session_duration
        if mins is None:
            return format_html('<span style="color:#16a34a;font-weight:600;">{}</span>', 'Still Active')
        if mins < 1:
            return badge('< 1 min', '#94a3b8', '⏱️')
        elif mins < 60:
            return badge(f'{int(mins)} min', '#6366f1', '⏱️')
        else:
            hours = round(mins / 60, 1)
            return badge(f'{hours}h', '#16a34a', '⏱️')


# ══════════════════════════════════════════════════════════════
#  ADMIN SITE BRANDING & DASHBOARD STATS
# ══════════════════════════════════════════════════════════════

admin.site.site_header = '🎓 StudySuite AI — Admin Panel'
admin.site.site_title = 'StudySuite AI'
admin.site.index_title = '📊 Dashboard — Manage All AI Tools'

_original_index = AdminSite.index


def _patched_index(self, request, extra_context=None):
    extra_context = extra_context or {}
    today = timezone.now().date()

    extra_context['dashboard_stats'] = {
        'total_quizzes': Quiz.objects.count(),
        'total_question_sets': QuestionSet.objects.count(),
        'total_study_plans': StudyPlan.objects.count(),
        'total_attempts': QuizAttempt.objects.count(),
        'today_quizzes': Quiz.objects.filter(created_at__date=today).count(),
        'today_question_sets': QuestionSet.objects.filter(created_at__date=today).count(),
        'today_plans': StudyPlan.objects.filter(created_at__date=today).count(),
        'active_sessions': UserLoginLog.objects.filter(is_active=True).count(),
        'guest_quizzes': Quiz.objects.filter(user__isnull=True).count(),
        'registered_quizzes': Quiz.objects.filter(user__isnull=False).count(),
    }
    return _original_index(self, request, extra_context)


AdminSite.index = _patched_index


# ══════════════════════════════════════════════════════════════
#  UPLOADED FILE ADMIN
# ══════════════════════════════════════════════════════════════

@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = (
        'original_filename', 'user_display', 'file_type_badge',
        'generation_badge', 'file_size_col', 'uploaded_at', 'view_link',
    )
    list_filter = ('generation_type', 'file_type', 'uploaded_at')
    search_fields = ('original_filename', 'user__email')
    readonly_fields = (
        'user', 'file', 'original_filename', 'file_type',
        'file_size_bytes', 'generation_type', 'uploaded_at',
        'quiz', 'question_set', 'study_plan',
    )
    ordering = ['-uploaded_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='User')
    def user_display(self, obj):
        if obj.user:
            return format_html(
                '<span style="color:#6366f1;font-weight:600;">👤 {}</span>',
                obj.user.email
            )
        return format_html('<span style="color:#94a3b8;">🌐 Guest</span>')

    @admin.display(description='File Type')
    def file_type_badge(self, obj):
        config = {
            'pdf': ('#ef4444', '📄'),
            'docx': ('#3b82f6', '📝'),
            'image': ('#10b981', '🖼️'),
            'youtube': ('#f59e0b', '▶️'),
            'text': ('#8b5cf6', '✏️'),
        }
        color, icon = config.get(obj.file_type, ('#94a3b8', '?'))
        return format_html(
            '<span style="background:{}22;color:{};padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;">{} {}</span>',
            color, color, icon, obj.get_file_type_display()
        )

    @admin.display(description='For')
    def generation_badge(self, obj):
        config = {
            'quiz': ('#4f46e5', '🧠'),
            'question': ('#0891b2', '📝'),
            'plan': ('#7c3aed', '📅'),
        }
        color, icon = config.get(obj.generation_type, ('#94a3b8', '?'))
        return format_html(
            '<span style="background:{}22;color:{};padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;">{} {}</span>',
            color, color, icon, obj.get_generation_type_display()
        )

    @admin.display(description='Size')
    def file_size_col(self, obj):
        return obj.file_size_display

    @admin.display(description='File')
    def view_link(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank" style="color:#6366f1;font-weight:600;">View →</a>',
                obj.file.url
            )
        if obj.file_type == 'youtube':
            return format_html(
                '<a href="{}" target="_blank" style="color:#f59e0b;font-weight:600;">YouTube →</a>',
                obj.original_filename
            )
        return format_html('<span style="color:#94a3b8;">—</span>')
