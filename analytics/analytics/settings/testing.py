from .base import *  # noqa: F403,F401

SECRET_KEY = "testingsecret"

# Testing will add 'testserver' to ALLOWED_HOSTS
ALLOWED_HOSTS: list[str] = []

# Testing will set EMAIL_BACKEND to use the memory backend
