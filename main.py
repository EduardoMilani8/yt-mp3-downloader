#!/usr/bin/env python3
"""Baixa o áudio de vídeos e playlists do YouTube e converte para MP3."""

import os
import sys

_VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python3")
_VENV_ROOT = os.path.normpath(os.path.join(os.path.dirname(_VENV_PYTHON), os.pardir))
_IN_VENV = os.environ.get("VIRTUAL_ENV") or (
    sys.prefix and os.path.realpath(sys.prefix) == os.path.realpath(_VENV_ROOT)
)
if __name__ == "__main__" and not _IN_VENV and os.path.exists(_VENV_PYTHON):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

import json
import re
import shutil

import yt_dlp
from tqdm import tqdm
from yt_dlp.utils import DownloadError

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".yt-mp3-config.json")
DEFAULT_CONFIG = {
    "saved_folders": [],
    "last_folder": None,
    "bitrate": "320",
    "filename_template": "{song} - {artist}",
}
MAX_FILENAME_LENGTH = 100
SAIR = {"sair", "exit", "quit", "s", "q"}
VALID_BITRATES = ("128", "192", "320")
INVALID_FS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_SONG_NOISE = [
    r"\(official\s+(music\s+)?video\)",
    r"\(official\s+audio\)",
    r"\(official\s+lyric(s)?\s+video\)",
    r"\(lyric(al)?\s+video\)",
    r"\(video\s+lyrics?\)",
    r"\(with\s+lyrics\)",
    r"\(lyrics?\)",
    r"\(visualizer\)",
    r"\(official\s+visualizer\)",
    r"\(live\s+session\)",
    r"\(live\)",
    r"\(audio\)",
    r"\(official\s+hq\)",
    r"\(music\s+video\)",
    r"\(hq\)",
    r"\(hd\)",
    r"\(4k\)",
    r"\(official\)",
]


# ---------------------------------------------------------------------------
# Configurações (JSON)
# ---------------------------------------------------------------------------
def load_config(path=CONFIG_FILE):
    """Carrega a configuração, mesclando com os padrões quando ausente."""
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key, default in DEFAULT_CONFIG.items():
                    value = loaded.get(key, default)
                    if key in loaded and value is not None:
                        config[key] = value
        except (OSError, json.JSONDecodeError):
            pass
    return config


def save_config(config, path=CONFIG_FILE):
    """Persiste a configuração em JSON."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"  Não foi possível salvar a configuração: {exc}")


# ---------------------------------------------------------------------------
# Checagens e utilitários de entrada
# ---------------------------------------------------------------------------
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


def is_playlist(url):
    """Considera como playlist qualquer link com o parâmetro 'list='."""
    return "list=" in url


def normalize_url(raw):
    """Normaliza um link, adicionando https:// quando faz sentido."""
    url = raw.strip().rstrip(".,;")
    if not url:
        return None
    url_clean = url.replace(",", "")
    m = re.match(r"^(https?://)?(www\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(/\S*)?$", url_clean)
    if not m:
        return None
    if not re.match(r"^https?://", url_clean, re.IGNORECASE):
        url_clean = "https://" + url_clean
    return url_clean


def load_links_from_file(path):
    """Lê links de um arquivo de texto (um link por linha)."""
    if not path:
        print("  Uso: /arquivo <caminho-do-arquivo.txt>")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        print(f"  Não foi possível ler o arquivo: {exc}")
        return None
    links = [normalize_url(line) for line in lines]
    links = [link for link in links if link]
    if not links:
        print("  Nenhum link válido encontrado no arquivo.")
        return None
    print(f"  {len(links)} link(s) carregado(s) do arquivo.")
    return links


def show_help():
    print()
    print("  Comandos disponíveis:")
    print("    /help                     - mostra esta ajuda")
    print("    /pastas                   - gerenciar pastas salvas")
    print("    /config                   - trocar o bitrate (128/192/320)")
    print("    /arquivo <caminho.txt>    - baixar links de um arquivo")
    print("    sair                      - encerrar o programa")
    print()
    print("  Dicas:")
    print("    - Para baixar vários links de uma vez, cole um por linha")
    print("      e termine com uma linha em branco (vira uma fila).")
    print("    - Na primeira escolha de pasta, digite N para salvar a pasta")
    print("      e ela passa a aparecer no menu das próximas vezes.")


def read_links(config):
    """Coleta links até uma linha em branco. Trata comandos.

    Retorna: lista de URLs, lista vazia (sem nada para fazer) ou None (sair).
    """
    urls = []
    while True:
        try:
            prompt = "Link > " if not urls else "  + mais links (Enter para baixar) > "
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not raw:
            if urls:
                return urls
            continue

        low = raw.lower()
        if low in SAIR:
            return None
        if low == "/help":
            show_help()
            continue
        if low in ("/pastas", "/pasta"):
            manage_folders(config)
            continue
        if low == "/config":
            change_bitrate(config)
            continue
        if low.startswith("/arquivo"):
            path = raw.split(" ", 1)[1] if " " in raw else ""
            loaded = load_links_from_file(path)
            if loaded is not None:
                urls.extend(loaded)
                if urls:
                    return urls
            continue
        if low.startswith("/"):
            print("  Comando desconhecido. Use /help para ver as opções.")
            continue

        tokens = [token.strip(" ,;") for token in re.split(r"\s+", raw)]
        added = 0
        for token in tokens:
            normalized = normalize_url(token)
            if normalized:
                urls.append(normalized)
                added += 1
            elif token:
                print(f"  Link inválido ignorado: {token[:60]}")
        if not added:
            print("  Link inválido: use o formato https://www.youtube.com/...")
        elif added > 1:
            print(f"  {added} links adicionados à fila.")


# ---------------------------------------------------------------------------
# Pastas salvas
# ---------------------------------------------------------------------------
def pick_folder():
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
    return folder or None


def add_folder(config):
    """Abre o seletor, pede um nome e salva a pasta na configuração."""
    folder = pick_folder()
    if not folder:
        print("  Nenhuma pasta foi selecionada.")
        return None

    default_name = os.path.basename(folder.rstrip(os.sep)) or "pasta"
    try:
        name = input(f"  Nome para salvar (Enter para '{default_name}') > ").strip()
    except (EOFError, KeyboardInterrupt):
        name = ""
    if not name:
        name = default_name

    saved = [
        item for item in config.get("saved_folders", [])
        if item["path"] != folder and item["name"] != name
    ]
    saved.append({"name": name, "path": folder})
    config["saved_folders"] = saved
    save_config(config)
    print(f"  Pasta '{name}' salva.")
    return folder


def manage_folders(config):
    """Menu para listar/adicionar/remover pastas salvas."""
    saved = list(config.get("saved_folders") or [])
    print()
    print("  Pastas salvas:")
    if not saved:
        print("    (nenhuma)")
    for i, item in enumerate(saved, 1):
        print(f"    [{i}] {item['name']}  ->  {item['path']}")
    print("    [A] Adicionar nova    [R] Remover    [C] Cancelar")
    try:
        opt = input("  Opção > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if opt in ("a", "adicionar", "add"):
        add_folder(config)
    elif opt in ("r", "remover", "remove"):
        if not saved:
            print("  Não há pastas para remover.")
            return
        try:
            which = input("  Remover qual pasta? (número) > ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not which.isdigit():
            print("  Cancelado.")
            return
        idx = int(which)
        if not 1 <= idx <= len(saved):
            print("  Número inválido.")
            return
        removed = saved[idx - 1]
        config["saved_folders"].remove(removed)
        if config.get("last_folder") == removed["path"]:
            config["last_folder"] = (
                config["saved_folders"][-1]["path"] if config["saved_folders"] else None
            )
        save_config(config)
        print(f"  Pasta '{removed['name']}' removida.")


def choose_folder(config):
    """Menu de pastas: última usada, salvas, nova ou cancelar."""
    saved = list(config.get("saved_folders") or [])
    last = config.get("last_folder") or ""

    print()
    print("  Pasta de destino:")
    if last:
        print(f"    [Enter] (última) {last}")
    for i, item in enumerate(saved, 1):
        print(f"    [{i}] {item['name']}  ->  {item['path']}")
    print("    [N] Escolher nova pasta...")
    print("    [C] Cancelar")

    while True:
        try:
            choice = input("  Escolha > ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        low = choice.lower()

        if not choice:
            if last:
                return last
            print("    Nenhuma pasta usada antes. Digite N para escolher uma.")
            continue
        if low in ("c", "cancelar", "sair"):
            return None
        if low in ("n", "nova", "novo", "add"):
            return add_folder(config)
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(saved):
                return saved[idx - 1]["path"]
        print(f"    Opção inválida. Use 1-{max(len(saved), 1)}, N ou C.")


def change_bitrate(config):
    """Altera o bitrate dos MP3."""
    print()
    print(f"  Bitrate atual: {config.get('bitrate', '320')} kbps")
    print("  Opções: 128, 192, 320")
    try:
        choice = input("  Novo bitrate (Enter para cancelar) > ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not choice:
        return
    if choice not in VALID_BITRATES:
        print("  Bitrate inválido. Use 128, 192 ou 320.")
        return
    config["bitrate"] = choice
    save_config(config)
    print(f"  Bitrate alterado para {choice} kbps.")


# ---------------------------------------------------------------------------
# Nomes de arquivo padronizados (Musica - Artista)
# ---------------------------------------------------------------------------
def clean_channel(channel):
    """Remove sufixos típicos de canal: ' - Topic', 'official', etc."""
    if not channel:
        return ""
    ch = channel.strip()
    ch = re.sub(r"(?i)-\s*topic\s*$", "", ch)
    ch = re.sub(r"(?i)-\s*official\s*(channel)?\s*$", "", ch)
    ch = re.sub(r"(?i)\s+official\s*$", "", ch)
    return ch.strip(" -–—|")


def clean_song_text(text):
    """Remove ruído comum de títulos: (Official Video), (Lyrics), [4k]..."""
    if not text:
        return ""
    s = text.strip()
    for pattern in _SONG_NOISE:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\([^)]*(?:official|video|lyrics?|audio|live|visualizer|hd|4k|hq)[^)]*\)",
        "", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\[[^\]]*(?:official|video|lyrics?|audio|live|visualizer|hd|4k|hq)[^\]]*\]",
        "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .-–—|")


def clean_artist_text(text):
    """Limpa o nome do artista/canal para uso no arquivo."""
    if not text:
        return ""
    s = re.sub(r"(?i)-\s*topic\s*$", "", text.strip())
    s = re.sub(r"(?i)-\s*official\s*(channel)?\s*$", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .-–—|")


def split_artist_song(title, artist_hint):
    """Separa 'Musica - Artista' usando o nome do canal como dica."""
    if not title:
        return "", clean_artist_text(artist_hint or "")
    hint = clean_artist_text(artist_hint or "")
    n_hint = re.sub(r"[^a-z0-9]", "", hint.lower())

    for sep in (" - ", " – ", " — ", " | "):
        if sep not in title:
            continue
        left, right = title.split(sep, 1)
        left, right = left.strip(), right.strip()
        n_left = re.sub(r"[^a-z0-9]", "", left.lower())
        n_right = re.sub(r"[^a-z0-9]", "", right.lower())
        if n_hint and n_hint in n_right:
            # Musica - Artista
            return left, right
        if n_hint and n_hint in n_left:
            # Artista - Musica
            return right, left
        return left, right
    return title, hint


def sanitize(name):
    """Remove caracteres inválidos e limita o tamanho do nome."""
    name = INVALID_FS.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" .")
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH].rstrip(" .-_")
    return name


def build_filename(info, config=None):
    """Monta o nome base do arquivo no formato 'Musica - Artista'."""
    config = config or {}
    template = config.get("filename_template") or "{song} - {artist}"
    title = (info.get("title") or "").strip()
    track = (info.get("track") or "").strip()
    artist = (info.get("artist") or info.get("creator") or "").strip()
    channel = clean_channel(info.get("uploader") or info.get("channel") or "")

    if track and artist:
        song, art = track, artist
    elif title:
        song, art = split_artist_song(title, channel or artist)
    else:
        song, art = track or "audio", artist or channel

    if not art and artist:
        art = artist
    if not song:
        song = title or track or "audio"

    song = clean_song_text(song) or song.strip() or "audio"
    art = clean_artist_text(art) if art else ""

    if art:
        name = template.format(song=song, artist=art)
    else:
        name = song
    return sanitize(name)


def unique_path(path):
    """Gera um caminho único, adicionando ' (2)', ' (3)'... quando já existe."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
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


class ProgressState:
    def __init__(self):
        self.bar = None


def make_progress_hook(state, progress_callback=None):
    """Hook de progresso: barra tqdm no terminal ou callback na interface web."""
    def hook(d):
        status = d.get("status")
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0

        if progress_callback is not None:
            if status == "downloading":
                progress_callback(
                    "downloading",
                    done=done,
                    total=total,
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                )
            elif status == "finished":
                progress_callback("finished")
            return

        if status == "downloading":
            if state.bar is None:
                state.bar = tqdm(
                    total=total or None,
                    unit="B",
                    unit_scale=True,
                    desc="  Baixando",
                    leave=False,
                )
            if total:
                state.bar.total = total
            state.bar.update(done - state.bar.n)
            parts = []
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            if speed:
                parts.append(speed)
            if eta:
                parts.append(f"restam {eta}")
            if parts:
                state.bar.set_postfix_str(" · ".join(parts), refresh=False)
        elif status == "finished":
            if state.bar is not None:
                if state.bar.total:
                    state.bar.update(state.bar.total - state.bar.n)
                state.bar.close()
                state.bar = None
            tqdm.write("\r  Download concluído. Convertendo para MP3...")

    return hook


def make_post_hook(folder, config, final_files):
    """Renomeia o MP3 gerado para o padrão 'Musica - Artista'."""
    def hook(d):
        if d.get("status") != "finished":
            return
        info = d.get("info_dict") or {}
        downloads = info.get("requested_downloads") or []
        if not downloads:
            return
        original = downloads[0].get("filepath") or ""
        if not original:
            return
        mp3_path = os.path.splitext(original)[0] + ".mp3"
        if not os.path.exists(mp3_path):
            return
        final_path = unique_path(os.path.join(folder, build_filename(info, config) + ".mp3"))
        try:
            os.replace(mp3_path, final_path)
        except OSError:
            final_path = mp3_path
        final_files.append(final_path)

    return hook


def download_audio(url, folder, config, progress_callback=None):
    """Baixa o(s) áudio(s), converte para MP3 e renomeia para o padrão.

    Se 'progress_callback' for fornecido (usado pela interface web), ela é
    chamada com os eventos "downloading" e "finished" em vez de exibir a
    barra tqdm do terminal.
    """
    final_files = []
    state = ProgressState()
    logger = ErrorLogger()
    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": config.get("bitrate", "320"),
            }
        ],
        "progress_hooks": [make_progress_hook(state, progress_callback)],
        "postprocessor_hooks": [make_post_hook(folder, config, final_files)],
        "logger": logger,
        "noplaylist": not is_playlist(url),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    return final_files, logger


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


def report(results, folder):
    """Exibe o resultado dos downloads com nome e caminho dos arquivos."""
    all_files = []
    errors = []
    for files, logger in results:
        all_files.extend(files or [])
        errors.extend(logger.errors or [])

    ok = [f for f in all_files if os.path.exists(f)]
    if ok:
        print()
        print(f"  {len(ok)} arquivo(s) salvo(s) com sucesso!")
        print(f"  Pasta: {os.path.abspath(folder)}")
        for f in ok:
            print(f"    - {os.path.basename(f)}")
        print()
        print("  Pronto para o próximo lote!")
        return

    print()
    print("  Nenhum arquivo foi salvo.")
    if errors:
        print(f"  Possível causa: {errors[-1][:300]}")
    else:
        print("  Verifique o link, se o vídeo está disponível e sua conexão.")


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print(" yt-mp3-downloader - baixa áudio do YouTube como MP3")
    print("=" * 60)

    if not check_ffmpeg():
        print("Instale o ffmpeg para continuar e rode o programa novamente.")
        return

    config = load_config()
    saved = config.get("saved_folders") or []
    if saved:
        print(f"  {len(saved)} pasta(s) salva(s). Use /pastas para gerenciar.")
    print(f"  Bitrate atual: {config.get('bitrate', '320')} kbps (use /config para mudar).")

    print()
    print("Cole o link de um vídeo ou playlist. Para baixar vários de uma vez,")
    print("cole os links um por linha e termine com uma linha em branco.")
    print("Comandos: /help   /pastas   /config   /arquivo <caminho.txt>")
    print("Digite 'sair' a qualquer momento para encerrar.")

    while True:
        print()
        urls = read_links(config)
        if urls is None:
            print()
            print("Encerrando. Até a próxima!")
            return
        if not urls:
            continue

        folder = choose_folder(config)
        if not folder:
            print("  Download cancelado.")
            continue

        config["last_folder"] = folder
        save_config(config)

        total = len(urls)
        print(f"  {total} item(ns) para baixar em: {folder}")
        results = []
        for i, url in enumerate(urls, 1):
            tag = f"[{i}/{total}] " if total > 1 else ""
            print(f"\n  {tag}Baixando: {url}")
            try:
                result = download_audio(url, folder, config)
            except DownloadError as exc:
                print(f"  Falha no download: {friendly_error(exc)}")
                continue
            except Exception as exc:
                print(f"  Erro inesperado: {exc}")
                continue
            results.append(result)
        report(results, folder)


if __name__ == "__main__":
    main()