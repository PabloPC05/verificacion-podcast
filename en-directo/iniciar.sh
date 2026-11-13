#!/bin/zsh
# Arranca el verificador. Opciones: ./iniciar.sh --help
cd "$(dirname "$0")" && exec ../.venv/bin/python verificador.py "$@"
