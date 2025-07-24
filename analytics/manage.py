#!/usr/bin/env python
import os
import sys

from django.core.management import execute_from_command_line

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "analytics.settings.production")


def main() -> None:
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
