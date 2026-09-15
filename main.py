#!/usr/bin/env python3
"""Baixa o áudio de vídeos e playlists do YouTube e converte para MP3 (320 kbps)."""

import os
import sys

_VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python3")
if not os.environ.get("VIRTUAL_ENV") and os.path.exists(_VENV_PYTHON):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

import re
import shutil

import yt_dlp
from yt_dlp.utils import DownloadError

MP3_BITRATE = "320"
MAX_FILENAME_LENGTH = 100
SAIR = {"sair", "exit", "quit", "s", "q"}


def check_ffmpeg():
    """Verifica se o ffmpeg está instalado e acessível no PATH."""
    if shutil.which("ffmpeg"):
        print("[OK] ffmpeg encontrado.")
        return True
    print()
    print("[ERRO] O ffmpeg não foi encontrado no sistema.")
    print("O ffmpeg é necessário para converter o áudio para MP3.")
    print()
    print("Como instalar:")
    print("  Linux (Debian/Ubuntu):  sudo apt update && sudo apt install ffmpeg")
    print("  Linux (Fedora):         sudo dnf install ffmpeg")
    print("  Linux (Arch):           sudo pacman -S ffmpeg")
    print("  macOS (Homebrew):       brew install ffmpeg")
    print("  Windows:                winget install ffmpeg")
    print()
    return False


def choose_folder():
    """Abre o seletor nativo de pasta do SO usando tkinter.filedialog."""
    try:
        from tkinter import Tk, filedialog
    except ImportError:
        print("[ERRO] O módulo 'tkinter' não está disponível.")
        print("  Linux:      sudo apt install python3-tk")
        print("  macOS:      use o instalador oficial do python.org")
        print("  Windows:    normalmente já vem junto com o Python")
        return None

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        folder = filedialog.askdirectory(
            title="Escolha a pasta para salvar o(s) MP3"
        )
    finally:
        root.destroy()
    return folder


def is_playlist(url):
    """Considera como playlist qualquer link com o parâmetro 'list='."""
    return "list=" in url


class ErrorLogger:
    """Captura mensagens de erro internas do yt-dlp para exibição amigável."""

    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(msg)


def download_audio(url, folder):
    """Baixa o(s) áudio(s) e converte para MP3, retornando os arquivos finais."""
    finished_files = []

    def progress_hook(d):
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            line = f"\r  Baixando {percent}"
            if speed:
                line += f" ({speed})"
            if eta:
                line += f" - restante: {eta}"
            print(f"{line}   ", end="", flush=True)
        elif d["status"] == "finished":
            print("\r  Download concluído. Convertendo para MP3...")

    def postprocessor_hook(d):
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            downloads = info.get("requested_downloads") or []
            if downloads:
                original = downloads[0].get("filepath")
                if original:
                    finished_files.append(os.path.splitext(original)[0] + ".mp3")

    logger = ErrorLogger()
    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": MP3_BITRATE,
            }
        ],
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "logger": logger,
        "noplaylist": not is_playlist(url),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "trim_file_name": MAX_FILENAME_LENGTH,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    return finished_files, logger


def friendly_error(exc):
    """Traduz a mensagem de erro do yt-dlp para algo compreensível."""
    msg = str(exc).lower()
    if "unsupported url" in msg or "not a valid url" in msg:
        return "o link informado parece ser inválido"
    if (
        "unable to download webpage" in msg
        or "timed out" in msg
        or "connection" in msg
    ):
        return "não foi possível conectar ao YouTube (verifique sua internet)"
    if "video unavailable" in msg:
        return "o vídeo está indisponível ou é privado"
    return "confira o link e tente novamente"


def report(result, folder):
    """Exibe o resultado do download com nome e caminho dos arquivos."""
    files, logger = result
    ok = [f for f in (files or []) if os.path.exists(f)]

    if ok:
        print()
        print(f"  {len(ok)} arquivo(s) salvo(s) com sucesso!")
        print(f"  Pasta: {os.path.abspath(folder)}")
        for f in ok:
            print(f"    - {os.path.basename(f)}")
        print()
        print("  Pronto para o próximo link!")
        return

    print()
    print("  Nenhum arquivo foi salvo.")
    if logger.errors:
        print(f"  Possível causa: {logger.errors[-1][:300]}")
    else:
        print("  Verifique o link, se o vídeo está disponível e sua conexão.")


def main():
    print("=" * 60)
    print(" yt-mp3-downloader - baixa áudio do YouTube como MP3 (320 kbps)")
    print("=" * 60)

    if not check_ffmpeg():
        print("Instale o ffmpeg para continuar e rode o programa novamente.")
        return

    print()
    print("Pronto para uso! Cole o link de um vídeo ou playlist abaixo.")
    print("Digite 'sair' a qualquer momento para encerrar.")

    while True:
        print()
        url = input("Link do YouTube > ").strip()
        if not url:
            continue
        if url.lower() in SAIR:
            print()
            print("Encerrando. Até a próxima!")
            break
        if not re.match(r"^https?://", url):
            print("  Link inválido: deve começar com http:// ou https://")
            continue

        folder = choose_folder()
        if not folder:
            print("  Nenhuma pasta foi selecionada - operação cancelada.")
            continue

        kind = "playlist" if is_playlist(url) else "vídeo"
        print(f"  Baixando {kind} para: {folder}")
        try:
            result = download_audio(url, folder)
        except DownloadError as exc:
            print(f"  Falha no download: {friendly_error(exc)}")
        except Exception as exc:
            print(f"  Erro inesperado: {exc}")
        else:
            report(result, folder)


if __name__ == "__main__":
    main()