from django.http import HttpResponse
from django.test import override_settings

from analytics.pipeline_status.middleware import (
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)


def _response_through_middleware(**existing_headers) -> HttpResponse:
    middleware = SecurityHeadersMiddleware(
        lambda request: HttpResponse("ok", headers=existing_headers)
    )
    return middleware(None)


@override_settings(DEBUG=False)
def test_security_headers_are_applied():
    response = _response_through_middleware()

    assert response["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


@override_settings(DEBUG=False)
def test_policy_allows_no_remote_origins_and_no_inline_scripts():
    # The point of vendoring the frontend assets is that this stays true.
    assert "default-src 'self'" in CONTENT_SECURITY_POLICY
    assert "script-src 'self' 'unsafe-eval'" in CONTENT_SECURITY_POLICY
    assert "https://" not in CONTENT_SECURITY_POLICY
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY.split("style-src")[0]
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "object-src 'none'" in CONTENT_SECURITY_POLICY


@override_settings(DEBUG=True)
def test_headers_are_skipped_under_debug():
    # django-debug-toolbar injects inline scripts that this policy would block.
    response = _response_through_middleware()

    assert "Content-Security-Policy" not in response


@override_settings(DEBUG=False)
def test_existing_headers_are_not_overwritten():
    response = _response_through_middleware(**{"Content-Security-Policy": "default-src 'none'"})

    assert response["Content-Security-Policy"] == "default-src 'none'"
