from django.urls import path
from . import views
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView
from .sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
}

urlpatterns = [
    path('', views.index, name='index'),  # Landing page
    path('quiz-generator/', views.home, name='home'),  # MCQ Generator
    path('quiz/<int:quiz_id>/', views.quiz, name='quiz'),
    path('result/<int:attempt_id>/', views.result, name='result'),
    path('question-generator/', views.question_generator, name='question_generator'),
    path('question-set/<int:set_id>/', views.question_set_detail, name='question_set'),
    path('study-planner/', views.study_planner, name='study_planner'),
    path('study-plan/<int:plan_id>/', views.study_plan_detail, name='study_plan_detail'),
    path('plans/', views.study_plans_list, name='study_plans_list'),
    path('study-plan/<int:plan_id>/pdf/', views.download_study_plan_pdf, name='download_study_plan_pdf'),
    path('study-plan/<int:plan_id>/delete/', views.delete_study_plan, name='delete_study_plan'),
    path('study-plan/<int:plan_id>/update-date/', views.update_exam_date, name='update_exam_date'),
    path('logout/', views.custom_logout, name='custom_logout'),
    path('api/remaining/', views.get_remaining_attempts, name='remaining_attempts'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', TemplateView.as_view(
        template_name='robots.txt',
        content_type='text/plain'
    ), name='robots'),
]
