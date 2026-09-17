#!/usr/bin/env python3
"""Interface web para o yt-mp3-downloader (Flask)."""

import os
import sys
import threading
import uuid
import webbrowser

_VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python3")
_VENV_ROOT = os.path.normpath(os.path.join(os.path.dirname(_VENV_PYTHON), os.pardir))
_IN_VENV = os.environ.get("VIRTUAL_ENV") or (
    sys.prefix and os.path.realpath(sys.prefix) == os.path.realpath(_VENV_ROOT)
)
if not _IN_VENV and os.path.exists(_VENV_PYTHON):
    os.execv(_VENV_PYTHON, [_VENV_PYTHON] + sys.argv)

import main  # noqa: E402  (reusa a lógica de download/renomeação/config)

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

app = Flask(__name__, static_folder="static")

JOBS = {}
JOBS_LOCK = threading.Lock()

PASTA_ATUAL_ERROR = "informe um caminho de pasta existente"


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
@app.get("/api/config")
def get_config():
    cfg = main.load_config()
    return jsonify({
        "saved_folders": cfg.get("saved_folders", []),
        "last_folder": cfg.get("last_folder"),
        "bitrate": cfg.get("bitrate", "320"),
        "filename_template": cfg.get("filename_template"),
    })


@app.post("/api/config")
def set_config():
    data = request.get_json(silent=True) or {}
    cfg = main.load_config()
    bitrate = str(data.get("bitrate", "")).strip()
    if bitrate in main.VALID_BITRATES:
        cfg["bitrate"] = bitrate
    main.save_config(cfg)
    return jsonify({"ok": True, "bitrate": cfg["bitrate"]})


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------
@app.post("/api/folder/pick")
def pick_folder():
    """Abre o seletor nativo de pasta (tkinter) na máquina local."""
    try:
        folder = main.pick_folder()
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Não foi possível abrir o seletor: {exc}"}), 500
    if not folder:
        return jsonify({"ok": False, "error": "Nenhuma pasta foi escolhida."}), 400
    return jsonify({"ok": True, "path": os.path.normpath(folder)})


@app.post("/api/folders")
def add_folder():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    path = str(data.get("path") or "").strip()
    if not path:
        return jsonify({"ok": False, "error": PASTA_ATUAL_ERROR}), 400
    if not os.path.isdir(path):
        return jsonify({"ok": False, "error": "A pasta não existe no computador."}), 400
    if not name:
        name = os.path.basename(path.rstrip(os.sep)) or "pasta"
    cfg = main.load_config()
    saved = [
        item for item in cfg.get("saved_folders", [])
        if item["path"] != path and item["name"] != name
    ]
    saved.append({"name": name, "path": os.path.normpath(path)})
    cfg["saved_folders"] = saved
    main.save_config(cfg)
    return jsonify({"ok": True, "folders": saved})


@app.delete("/api/folders/<name>")
def remove_folder(name):
    cfg = main.load_config()
    cfg["saved_folders"] = [
        item for item in cfg.get("saved_folders", []) if item["name"] != name
    ]
    compatible = any(item["path"] == cfg.get("last_folder")
                     for item in cfg["saved_folders"])
    if not compatible:
        cfg["last_folder"] = (
            cfg["saved_folders"][-1]["path"] if cfg["saved_folders"] else None
        )
    main.save_config(cfg)
    return jsonify({"ok": True, "folders": cfg["saved_folders"]})


# ---------------------------------------------------------------------------
# Downloads (jobs)
# ---------------------------------------------------------------------------
def _job_to_dict(job):
    return {
        "id": job["id"],
        "folder": job["folder"],
        "bitrate": job["bitrate"],
        "cancelled": bool(job.get("cancelled")),
        "done": bool(job["done"]),
        "files": list(job["files"]),
        "items": list(job["items"]),
    }


def _new_item(url):
    return {
        "url": url,
        "status": "pending",
        "percent": 0,
        "done_bytes": 0,
        "total_bytes": 0,
        "speed": None,
        "eta": None,
        "message": None,
        "files": [],
    }


def run_job(job):
    """Executa os downloads em sequência, atualizando o estado do job."""
    for item in job["items"]:
        if job.get("cancelled"):
            if item["status"] == "pending":
                item["status"] = "cancelled"
            continue

        item["status"] = "downloading"
        item["message"] = None

        def progress(phase, **kwargs):
            if phase == "downloading":
                item["status"] = "downloading"
                item["done_bytes"] = kwargs.get("done", 0)
                item["total_bytes"] = kwargs.get("total", 0)
                total = item["total_bytes"]
                item["percent"] = round(item["done_bytes"] / total * 100, 1) if total else 0
                item["speed"] = kwargs.get("speed")
                item["eta"] = kwargs.get("eta")
            elif phase == "finished":
                item["status"] = "converting"
                item["percent"] = 100

        try:
            files, logger = main.download_audio(
                item["url"],
                job["folder"],
                {"bitrate": job["bitrate"]},
                progress_callback=progress,
            )
        except Exception as exc:
            item["status"] = "error"
            item["message"] = main.friendly_error(exc)
            continue

        if files:
            item["status"] = "done"
            item["percent"] = 100
            item["files"] = list(files)
            job["files"].extend(files)
        else:
            item["status"] = "error"
            item["percent"] = 0
            item["message"] = (
                logger.errors[-1][:300]
                if logger.errors
                else "verifique o link, se o vídeo está disponível e sua conexão"
            )

    job["done"] = True


@app.post("/api/jobs")
def start_job():
    data = request.get_json(silent=True) or {}
    folder = str(data.get("folder") or "").strip()
    links = data.get("links") or []
    bitrate = str(data.get("bitrate") or "320").strip()

    if not folder:
        return jsonify({"ok": False, "error": "Escolha a pasta de destino."}), 400
    if not os.path.isdir(folder):
        return jsonify({"ok": False, "error": "A pasta de destino não existe no computador."}), 400
    if bitrate not in main.VALID_BITRATES:
        bitrate = "320"

    urls = []
    for raw in links:
        url = main.normalize_url(str(raw))
        if url:
            urls.append(url)
    if not urls:
        return jsonify({"ok": False, "error": "Informe pelo menos um link válido."}), 400

    cfg = main.load_config()
    cfg["last_folder"] = folder
    main.save_config(cfg)

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "folder": folder,
        "bitrate": bitrate,
        "items": [_new_item(url) for url in urls],
        "files": [],
        "cancelled": False,
        "done": False,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return jsonify({"ok": True, "id": job_id})


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Download não encontrado."}), 404
    job["cancelled"] = True
    return jsonify({"ok": True})


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Download não encontrado."}), 404
    return jsonify({"ok": True, "job": _job_to_dict(job)})


@app.get("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        return jsonify({"ok": True, "jobs": [_job_to_dict(j) for j in JOBS.values()]})


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
def run():
    port = int(os.environ.get("YT_MP3_PORT", "8000"))
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print(" yt-mp3-downloader - interface web")
    print("=" * 60)
    if not main.check_ffmpeg():
        print("ATENÇÃO: sem o ffmpeg os downloads não vão funcionar.")
    print()
    print(f"  Acesse: {url}")
    print("  Pressione Ctrl+C para encerrar.")
    print()
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True)


if __name__ == "__main__":
    run()