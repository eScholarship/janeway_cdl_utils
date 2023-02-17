from django.conf.urls import url

from plugins.cdl_utils import views


urlpatterns = [
    url(r'^manager/$', views.cdl_utils_manager, name='cdl_utils_manager'),
]
