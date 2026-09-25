"""URL configuration for the internet-facing pipeline status deployment.

The default urlconf (analytics.urls) also serves the GitLab webhook handler, which
is unauthenticated and CSRF-exempt by necessity and must only ever be reachable from
inside the cluster. Rather than rely on the gateway to keep that endpoint private,
the public deployment runs this urlconf, which simply does not contain it.

See analytics/settings/public.py, and k8s/production/custom/pipeline-status/.
"""

from django.urls import include, path

from analytics.pipeline_status.views import robots_txt

urlpatterns = [
    path("robots.txt", robots_txt),
    # Kept under a path prefix (rather than served at the root) so that the gateway
    # can route only this prefix. That way a misconfigured DJANGO_SETTINGS_MODULE is
    # not by itself enough to expose the webhook handler.
    path("pipelines/", include("analytics.pipeline_status.urls")),
]
