from django.urls import re_path

from mutint_specificity import views

urlpatterns = [
    re_path(r'^$', views.specificity, name='specificity'),
    re_path(r'^status/(?P<pk>\d+)$', views.status, name='specificity_status'),
    re_path(r'^download/(?P<pk>\d+)/(?P<what>genes|matrix)\.csv$', views.download,
            name='specificity_download'),
]
