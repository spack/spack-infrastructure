"""Security response headers for the internet-facing pipeline status page.

The page renders strings that come from GitLab -- branch names, job names, failure
reasons -- which are ultimately attacker-influenceable: anyone can open a PR whose
branch name contains markup. Django's template autoescaping is the primary defence
against that; this Content-Security-Policy is the backstop, and is what makes the
"vendor the frontend assets" decision worth the trouble.

Because every asset is served from our own origin, the policy needs no third-party
hosts and no 'unsafe-inline' for scripts.
"""

from django.conf import settings

# Alpine.js evaluates the expressions in x-data/x-show/@click attributes, which needs
# 'unsafe-eval'. That is inherent to using Alpine without a build step; it is
# acceptable here because the only scripts that can run at all are our own (there is
# no 'unsafe-inline' for script-src, and no remote origin is allowed), so there is no
# path for injected markup to introduce a script for Alpine to evaluate.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-eval'",
        # DaisyUI sets CSS custom properties via inline style attributes on some
        # components, and the compiled stylesheet is served from our own origin.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        # The page never talks to anything but its own origin.
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "object-src 'none'",
    ]
)


class SecurityHeadersMiddleware:
    """Add a strict CSP and related headers to every response.

    Disabled under DEBUG, because django-debug-toolbar injects inline scripts and
    styles that a policy this strict would block. The policy is asserted by tests
    rather than by loading the page in development.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if settings.DEBUG:
            return response

        response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        # The page is not useful to search engines and every URL costs a database
        # query, so keep it out of indexes. robots.txt asks; this tells.
        response.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        return response
