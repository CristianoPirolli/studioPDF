import io
import shutil
import time
import uuid
from pathlib import Path
from typing import List

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from app.services.pdf_merge import PdfMergeError, apply_ocr, merge_with_header, validate_pdf


bp = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {".pdf"}


def _tmp_root() -> Path:
    return Path(current_app.config["TMP_ROOT"])


def _session_id() -> str:
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _session_dir() -> Path:
    return _tmp_root() / "sessions" / _session_id()


def _fixed_path() -> Path:
    return _session_dir() / "header.pdf"


def _job_dir(job_id: str) -> Path:
    return _tmp_root() / "jobs" / job_id


def _cleanup_old_dirs():
    ttl_seconds = current_app.config.get("CLEANUP_TTL_HOURS", 24) * 3600
    now = time.time()
    for group in ["sessions", "jobs"]:
        base = _tmp_root() / group
        if not base.exists():
            continue
        for path in base.iterdir():
            try:
                mtime = path.stat().st_mtime
                if now - mtime > ttl_seconds:
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                continue


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _file_size_ok(file_storage) -> bool:
    file_storage.stream.seek(0, io.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size <= current_app.config["MAX_FILE_SIZE"]


@bp.before_request
def before_request():
    _cleanup_old_dirs()


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/fixed")
def fixed_status():
    exists = _fixed_path().exists()
    return jsonify({"has_fixed": exists})


@bp.post("/api/fixed")
def upload_fixed():
    if "fixed" not in request.files:
        return jsonify({"error": "Arquivo de cabeçalho ausente"}), 400

    file = request.files["fixed"]
    if file.filename == "":
        return jsonify({"error": "Arquivo de cabeçalho vazio"}), 400

    if not _allowed(file.filename):
        return jsonify({"error": "Apenas PDF"}), 400

    if not _file_size_ok(file):
        return jsonify({"error": "Cabeçalho excede limite"}), 400

    session_dir = _session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename)
    target = _fixed_path()
    file.save(target)

    try:
        validate_pdf(target)
    except PdfMergeError as exc:
        target.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"ok": True, "name": filename})


@bp.delete("/api/fixed")
def clear_fixed():
    path = _fixed_path()
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})


@bp.post("/api/merge")
def merge_pdfs():
    if not _fixed_path().exists():
        return jsonify({"error": "Cabeçalho não definido"}), 400

    if "attachments" not in request.files:
        return jsonify({"error": "Nenhum PDF anexado"}), 400

    files = request.files.getlist("attachments")
    valid_files = [f for f in files if f and f.filename]
    if not valid_files:
        return jsonify({"error": "Nenhum PDF anexado"}), 400

    job_id = uuid.uuid4().hex
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors: List[str] = []

    for f in valid_files:
        if not _allowed(f.filename):
            errors.append(f"{f.filename}: apenas PDF")
            continue
        if not _file_size_ok(f):
            errors.append(f"{f.filename}: excede limite")
            continue

        safe_name = secure_filename(f.filename)
        input_path = job_dir / f"input__{safe_name}"
        output_name = f"merged__{safe_name}"
        output_path = job_dir / output_name

        f.save(input_path)
        try:
            validate_pdf(input_path)

            header_path = _fixed_path()
            attach_path = input_path

            # Debug log
            debug_log = job_dir / "debug.log"
            with debug_log.open("a", encoding="utf-8") as f:
                f.write(f"OCR_ENABLED: {current_app.config.get('OCR_ENABLED', False)}\n")
                f.write(f"OCR_LANGS: {current_app.config.get('OCR_LANGS', 'N/A')}\n")

            if current_app.config.get("OCR_ENABLED", False):
                with debug_log.open("a", encoding="utf-8") as f:
                    f.write("Entrando no bloco de OCR\n")

                ocr_langs = current_app.config.get("OCR_LANGS", "por")

                ocr_header = _session_dir() / "header_ocr.pdf"
                header_log = job_dir / "ocr__header.log"
                if not ocr_header.exists() or ocr_header.stat().st_mtime < header_path.stat().st_mtime:
                    with debug_log.open("a", encoding="utf-8") as f:
                        f.write(f"Aplicando OCR no header: {header_path}\n")
                    apply_ocr(header_path, ocr_header, ocr_langs, header_log)
                header_path = ocr_header

                ocr_attach = job_dir / f"ocr__{safe_name}"
                attach_log = job_dir / f"ocr__attach__{safe_name}.log"
                with debug_log.open("a", encoding="utf-8") as f:
                    f.write(f"Aplicando OCR no anexo: {attach_path}\n")
                apply_ocr(attach_path, ocr_attach, ocr_langs, attach_log)
                attach_path = ocr_attach
                with debug_log.open("a", encoding="utf-8") as f:
                    f.write("OCR aplicado com sucesso\n")

            merge_with_header(header_path, attach_path, output_path)
            results.append({
                "name": output_name,
                "url": f"/download/{job_id}/{output_name}",
                "preview_url": f"/preview/{job_id}/{output_name}",
            })
        except PdfMergeError as exc:
            debug_log = job_dir / "debug.log"
            with debug_log.open("a", encoding="utf-8") as f:
                f.write(f"ERRO: {exc}\n")
            errors.append(f"{safe_name}: {exc}")
        finally:
            input_path.unlink(missing_ok=True)
            if "ocr_attach" in locals():
                ocr_attach.unlink(missing_ok=True)

    if not results:
        return jsonify({"error": "Falha ao gerar PDFs", "details": errors}), 400

    return jsonify({"job_id": job_id, "files": results, "errors": errors})


def _resolve_job_file(job_id: str, filename: str) -> Path:
    job_dir = _job_dir(job_id)
    return job_dir / secure_filename(filename)


@bp.get("/download/<job_id>/<filename>")
def download(job_id: str, filename: str):
    file_path = _resolve_job_file(job_id, filename)
    if not file_path.exists():
        return jsonify({"error": "Arquivo não encontrado"}), 404
    return send_file(file_path, as_attachment=True, download_name=filename)


@bp.get("/preview/<job_id>/<filename>")
def preview(job_id: str, filename: str):
    file_path = _resolve_job_file(job_id, filename)
    if not file_path.exists():
        return jsonify({"error": "Arquivo não encontrado"}), 404
    return send_file(file_path, as_attachment=False, download_name=filename)
