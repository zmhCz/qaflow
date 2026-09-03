import json
import re

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def _validate_phone(phone):
    """Validate mainland China phone numbers used by the current user profile."""
    if not phone:
        return False, '请输入手机号'
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return False, '手机号格式不正确'
    return True, ''


@csrf_exempt
@require_http_methods(["POST"])
def test_register(request):
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        password_confirm = data.get('password_confirm', '')

        if not username:
            return JsonResponse({'success': False, 'error': '请输入用户名'}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': '用户名已存在'}, status=400)

        valid, error = _validate_phone(phone)
        if not valid:
            return JsonResponse({'success': False, 'error': error}, status=400)
        if User.objects.filter(phone=phone).exists():
            return JsonResponse({'success': False, 'error': '该手机号已被注册'}, status=400)

        if not email:
            return JsonResponse({'success': False, 'error': '请输入邮箱'}, status=400)
        if User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'error': '邮箱已被注册'}, status=400)

        if not password:
            return JsonResponse({'success': False, 'error': '请输入密码'}, status=400)
        if len(password) < 6:
            return JsonResponse({'success': False, 'error': '密码长度不能少于 6 位'}, status=400)
        if password != password_confirm:
            return JsonResponse({'success': False, 'error': '两次输入的密码不一致'}, status=400)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone=phone,
            department=data.get('department', ''),
            position=data.get('position', '')
        )

        refresh = RefreshToken.for_user(user)

        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'phone': user.phone,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'department': user.department,
                'position': user.position,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '请求数据格式错误'}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
