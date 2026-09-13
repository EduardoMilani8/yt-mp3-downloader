# yt-mp3-downloader

Baixa o áudio de vídeos e playlists do YouTube e converte automaticamente
para MP3 (320 kbps), salvando direto na pasta que você escolher.

Feito para uso pessoal — ideal para colocar músicas em um MP3 player físico.

## Como funciona

1. O programa inicia e fica aguardando você colar um link do YouTube.
2. Você escolhe a pasta de destino em um seletor nativo do sistema.
3. O áudio é baixado com `yt-dlp` e convertido para MP3 com `ffmpeg`.
   - Link de **vídeo único**: baixa 1 MP3 com o título do vídeo.
   - Link de **playlist** (contém `list=`): baixa cada vídeo como um MP3 separado.
4. O progresso do download aparece no terminal.
5. Ao final, mostra o(s) nome(s) do(s) arquivo(s) e o caminho onde foram salvos.
6. Digite `sair` a qualquer momento para encerrar.

Os nomes dos arquivos usam o título do vídeo, já sanitizado pelo `yt-dlp`
(remove caracteres inválidos para nome de arquivo).

## Requisitos

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/) instalado e acessível no terminal
- `pip` (ou pipx/venv) para instalar as dependências

### Instalação do ffmpeg

- **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
- **Linux (Fedora):** `sudo dnf install ffmpeg`
- **Linux (Arch):** `sudo pacman -S ffmpeg`
- **macOS (Homebrew):** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg`

## Como rodar

```bash
# 1. (opcional, recomendado) criar um ambiente virtual
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows (cmd)

# 2. instalar as dependências
pip install -r requirements.txt

# 3. iniciar
python main.py
```

O programa verifica se o `ffmpeg` está instalado logo no início e dá
instruções caso não esteja.

## Dependências

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download e extração de áudio
- `tkinter` — seletor de pasta nativo (já incluído na maioria das instalações
  de Python; no Debian/Ubuntu: `sudo apt install python3-tk`)
- `ffmpeg` — conversão para MP3 (invocado internamente pelo yt-dlp)