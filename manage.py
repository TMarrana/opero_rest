#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# O hosting local e o tunel HTTPS assentam nesta porta; ver .env.example.
DEFAULT_ADDRPORT = '127.0.0.1:8001'


def runserver_argv(argv):
    """Acrescenta o endereco por omissao ao runserver sem argumento posicional."""
    if len(argv) > 1 and argv[1] == 'runserver':
        if not any(not arg.startswith('-') for arg in argv[2:]):
            return argv + [DEFAULT_ADDRPORT]
    return argv


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(runserver_argv(sys.argv))


if __name__ == '__main__':
    main()
