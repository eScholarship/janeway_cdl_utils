from django.urls import re_path

from plugins.cdl_utils import views


urlpatterns = [
    re_path(r'^manager/$', views.cdl_utils_manager, name='cdl_utils_manager'),
]
