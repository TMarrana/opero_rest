"""Compila o Tailwind (binario standalone, sem npm): python manage.py css [--watch] [--minify]."""
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DOWNLOAD = "https://github.com/tailwindlabs/tailwindcss/releases/tag/v3.4.17"


def caminho_binario(base):
    """TAILWIND_BIN, senao tools/tailwindcss.exe no Windows, senao tools/tailwindcss."""
    definido = os.environ.get("TAILWIND_BIN")
    if definido:
        return Path(definido)
    nome = "tailwindcss.exe" if sys.platform == "win32" else "tailwindcss"
    return Path(base) / "tools" / nome


class Command(BaseCommand):
    help = "Compila static/src/input.css para static/css/app.css com o Tailwind standalone."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Recompila ao alterar ficheiros.")
        parser.add_argument("--minify", action="store_true", help="Minifica o CSS.")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        binario = caminho_binario(base)
        if not binario.is_file():
            raise CommandError(
                f"Binario do Tailwind nao encontrado: {binario}. "
                f"Descarregue a versao v3.4.17 para o seu sistema em {DOWNLOAD} "
                "e ponha-o em tools/ (ou defina TAILWIND_BIN)."
            )
        saida = base / "static" / "css" / "app.css"
        comando = [
            str(binario),
            "-i", str(base / "static" / "src" / "input.css"),
            "-o", str(saida),
        ]
        if options["watch"]:
            comando.append("--watch")
        if options["minify"]:
            comando.append("--minify")
        try:
            resultado = subprocess.run(comando, cwd=base)
        except KeyboardInterrupt:
            return
        except OSError as exc:
            raise CommandError(
                f"Nao foi possivel correr o Tailwind ({binario}): {exc.strerror or exc}. "
                "Em Linux e macOS, de-lhe permissao de execucao: chmod +x."
            ) from exc
        if resultado.returncode:
            raise CommandError(f"O Tailwind terminou com o codigo {resultado.returncode}.")
        # O Tailwind nao reescreve um CSS igual ao que ja la estava; sem isto a
        # data do ficheiro ficava antiga e o check opero.W001 nunca se calava.
        os.utime(saida)
