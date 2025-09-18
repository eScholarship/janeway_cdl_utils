from django.http import HttpResponse
from django.views.generic import TemplateView

def cdl_utils_manager(request):
    return HttpResponse("CDL Utils Plugin")

class LoginDisabledView(TemplateView):
    template_name = "cdl_utils/login_disabled.html"
