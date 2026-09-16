# yt-mp3-downloader

Baixa o áudio de vídeos e playlists do YouTube e converte automaticamente
para MP3, salvando direto na pasta que você escolher.

Feito para uso pessoal — ideal para colocar músicas em um MP3 player físico.

## Como funciona

1. O programa inicia e fica aguardando você colar um link do YouTube.
2. Para cada lote, você escolhe a pasta de destino — as pastas escolhidas
   ficam **salvas** e aparecem num menu numerado nas próximas vezes.
3. O áudio é baixado com `yt-dlp` e convertido para MP3 com `ffmpeg`.
   - Link de **vídeo único**: baixa 1 MP3 com o título do vídeo.
   - Link de **playlist** (contém `list=`): baixa cada vídeo como um MP3 separado.
4. O progresso do download aparece numa **barra visual** com velocidade e
   tempo restante.
5. Os arquivos são **renomeados no padrão `Musica - Artista`** (ex.:
   `Believer - Imagine Dragons.mp3`), detectando o artista a partir dos
   metadados, do canal (`- Topic`) ou do próprio título.
6. Ao final, mostra o(s) nome(s) do(s) arquivo(s) e o caminho onde foram salvos.
7. Digite `sair` a qualquer momento para encerrar.

É possível baixar **vários links de uma vez**: cole os links um por linha
e termine com uma linha em branco para iniciar a fila.

## Nomes dos arquivos

O padrão é `Musica - Artista` (configurável em `.yt-mp3-config.json` na chave
`filename_template`). A ordem de resolução é:

1. Metadados `track` + `artist` fornecidos pelo YouTube.
2. Canal automático `Artista - Topic` → artista = canal, música = título.
3. Título com ` - ` → detecta qual lado bate com o nome do canal/uploader.
4. Sem informação → usa o título como veio (após limpeza de ruído).

Ruídos comuns são removidos automaticamente: `(Official Video)`, `(Lyrics)`,
`(Audio)`, `[4K]`, etc. Nomes duplicados ganham sufixo ` (2)`, ` (3)`...

## Comandos dentro do programa

| Comando | O que faz |
| --- | --- |
| `/help` | Mostra a ajuda |
| `/pastas` | Gerencia pastas salvas (adicionar/remover) |
| `/config` | Troca o bitrate dos MP3 (128/192/320) |
| `/arquivo <caminho.txt>` | Baixa uma lista de links de um arquivo (um por linha) |
| `sair` | Encerra o programa |

## Configuração

A configuração fica em `.yt-mp3-config.json` (na mesma pasta do app) e guarda
as pastas salvas, a última pasta usada, o bitrate e o modelo de nome.
Ela é gerida pelos próprios comandos acima — não precisa editar na mão.

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
- `tqdm` — barra de progresso visual
- `tkinter` — seletor de pasta nativo (já incluído na maioria das instalações
  de Python; no Debian/Ubuntu: `sudo apt install python3-tk`)
- `ffmpeg` — conversão para MP3 (invocado internamente pelo yt-dlp)