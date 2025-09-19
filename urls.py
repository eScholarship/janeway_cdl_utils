from django.urls import re_path
from django.conf import settings

from plugins.cdl_utils.views import cdl_utils_manager
from plugins.cdl_utils.views import LoginDisabledView


urlpatterns = [
    re_path(r'^manager/$', cdl_utils_manager, name='cdl_utils_manager'),
]

if settings.DISABLE_LOGIN:
    urlpatterns.append(
        re_path(r'^login_disabled/$', LoginDisabledView.as_view(), name='login_disabled'),
    )
