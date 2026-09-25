from django.urls import path

from analytics.pipeline_status import views

app_name = "pipeline-status"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "<slug:org>/<slug:repo>/pull/<int:pr_number>/",
        views.pull_request,
        name="pull-request",
    ),
]
