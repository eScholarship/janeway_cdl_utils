from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings

class DisableLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'DISABLE_LOGIN', False) and \
           ("/login/" in request.path or "review/requests" in request.path):
            return HttpResponseRedirect(reverse('login_disabled'))

        response = self.get_response(request)
        return response