from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import UserLoginLog

site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')


def get_client_ip(request):
    """Real IP Address nikalne ke liye helper function."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    email = getattr(user, 'email', None) or getattr(user, 'username', 'Unknown')
    ip = get_client_ip(request)
    now_ist = timezone.localtime(timezone.now())

    # Previous active sessions auto-close karo
    UserLoginLog.objects.filter(
        email=email,
        is_active=True,
        logout_at__isnull=True
    ).update(
        is_active=False,
        logout_at=timezone.now()
    )

    # Naya login record banao
    UserLoginLog.objects.create(
        email=email,
        login_at=timezone.now(),
        ip_address=ip,
        is_active=True
    )

    # Welcome / Sign-in notification email
    try:
        is_first_login = not UserLoginLog.objects.filter(
            email=email
        ).exclude(login_at=None).count() > 1

        if is_first_login:
            subject = "Welcome to StudySuite AI! 🎓"
            message_html = f"""
            <div style="font-family: 'Plus Jakarta Sans', Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #f8fafc; padding: 32px 24px; border-radius: 16px;">

                <!-- Header -->
                <div style="background: #4f46e5; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 24px;">
                    <h1 style="color: white; font-size: 24px; margin: 0; font-weight: 800;">
                        StudySuite<span style="color: #a5b4fc;">AI</span>
                    </h1>
                    <p style="color: #c7d2fe; margin: 6px 0 0; font-size: 13px;">Your Complete AI Learning Suite</p>
                </div>

                <!-- Body -->
                <div style="background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px;">
                    <h2 style="color: #1e293b; font-size: 20px; margin: 0 0 12px;">Welcome aboard! 🎉</h2>
                    <p style="color: #475569; font-size: 14px; line-height: 1.6; margin: 0 0 16px;">
                        You have successfully signed in to <strong>StudySuite AI</strong> using your Google account.
                    </p>

                    <div style="background: #f1f5f9; border-radius: 8px; padding: 14px 16px; margin-bottom: 20px;">
                        <p style="margin: 0; font-size: 13px; color: #64748b;">
                            📧 <strong>Email:</strong> {email}<br>
                            🕐 <strong>Time:</strong> {now_ist.strftime('%d %B %Y, %I:%M %p')} IST
                        </p>
                    </div>

                    <p style="color: #475569; font-size: 14px; line-height: 1.6; margin: 0 0 20px;">
                        Here's what you can do with StudySuite AI:
                    </p>

                    <div style="display: grid; gap: 10px;">
                        <div style="background: #f0fdf4; border-left: 3px solid #22c55e; padding: 10px 14px; border-radius: 6px;">
                            <strong style="color: #15803d; font-size: 13px;">🧠 AI MCQ Quiz Generator</strong>
                            <p style="color: #4b5563; font-size: 12px; margin: 3px 0 0;">Upload PDF, Word, Image or YouTube URL — get instant quizzes</p>
                        </div>
                        <div style="background: #eff6ff; border-left: 3px solid #3b82f6; padding: 10px 14px; border-radius: 6px;">
                            <strong style="color: #1d4ed8; font-size: 13px;">📝 AI Question Generator</strong>
                            <p style="color: #4b5563; font-size: 12px; margin: 3px 0 0;">Generate FITB, True/False, Short & Long questions instantly</p>
                        </div>
                        <div style="background: #fdf4ff; border-left: 3px solid #a855f7; padding: 10px 14px; border-radius: 6px;">
                            <strong style="color: #7e22ce; font-size: 13px;">📅 AI Study Planner</strong>
                            <p style="color: #4b5563; font-size: 12px; margin: 3px 0 0;">Get a personalized day-by-day study schedule for your exam</p>
                        </div>
                    </div>
                </div>

                <!-- CTA Button -->
                <div style="text-align: center; margin-bottom: 20px;">
                    <a href="{site_url}"
                       style="background: #4f46e5; color: white; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block;">
                        Start Studying Now →
                    </a>
                </div>

                <!-- Footer -->
                <p style="text-align: center; color: #94a3b8; font-size: 11px; margin: 0;">
                    © 2026 StudySuite AI • You received this because you signed in with Google
                </p>
            </div>
            """
        else:
            subject = "New Sign-in to StudySuite AI 🔐"
            message_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #f8fafc; padding: 32px 24px; border-radius: 16px;">
                <div style="background: #4f46e5; border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 24px;">
                    <h1 style="color: white; font-size: 22px; margin: 0; font-weight: 800;">
                        StudySuite<span style="color: #a5b4fc;">AI</span>
                    </h1>
                </div>
                <div style="background: white; border-radius: 12px; padding: 24px;">
                    <h2 style="color: #1e293b; font-size: 18px; margin: 0 0 12px;">New Sign-in Detected 🔐</h2>
                    <p style="color: #475569; font-size: 14px; line-height: 1.6; margin: 0 0 16px;">
                        A new sign-in to your StudySuite AI account was detected.
                    </p>
                    <div style="background: #f1f5f9; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;">
                        <p style="margin: 0; font-size: 13px; color: #64748b;">
                            📧 <strong>Email:</strong> {email}<br>
                            🕐 <strong>Time:</strong> {now_ist.strftime('%d %B %Y, %I:%M %p')} IST<br>
                            🌐 <strong>IP:</strong> {ip}
                        </p>
                    </div>
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                        If this wasn't you, please contact us immediately.
                    </p>
                </div>
                <p style="text-align: center; color: #94a3b8; font-size: 11px; margin: 16px 0 0;">
                    © 2026 StudySuite AI
                </p>
            </div>
            """

        send_mail(
            subject=subject,
            message=f'You have signed in to StudySuite AI. Email: {email}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=message_html,
            fail_silently=True,
        )
    except Exception:
        pass


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user and getattr(user, 'is_authenticated', False):
        email = getattr(user, 'email', None) or getattr(user, 'username', None)
        if email:
            log = UserLoginLog.objects.filter(
                email=email,
                is_active=True,
                logout_at__isnull=True
            ).order_by('-login_at').first()

            if log:
                log.logout_at = timezone.now()
                log.is_active = False
                log.save()
