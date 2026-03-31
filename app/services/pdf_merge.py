from pathlib import Path
import subprocess
import sys
from pypdf import PdfReader, PdfWriter


class PdfMergeError(Exception):
    pass


def validate_pdf(path: Path) -> None:
    try:
        reader = PdfReader(str(path))
        if len(reader.pages) == 0:
            raise PdfMergeError("PDF sem páginas")
    except Exception as exc:
        raise PdfMergeError("PDF inválido") from exc


def merge_with_header(header_path: Path, attachment_path: Path, output_path: Path) -> None:
    try:
        header_reader = PdfReader(str(header_path))
        attachment_reader = PdfReader(str(attachment_path))
        writer = PdfWriter()

        for page in header_reader.pages:
            writer.add_page(page)

        for page in attachment_reader.pages:
            writer.add_page(page)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            writer.write(f)
    except Exception as exc:
        raise PdfMergeError("Falha ao gerar PDF") from exc


def apply_ocr(input_path: Path, output_path: Path, langs: str, log_path: Path) -> None:
    try:
        cmd = [
            sys.executable,
            "-m",
            "ocrmypdf",
            "--skip-text",  # Apenas páginas sem texto (muito mais rápido)
            "--output-type", "pdf",  # PDF normal, não PDF/A (mais rápido)
            "-l",
            langs,
            str(input_path),
            str(output_path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"COMMAND: {' '.join(cmd)}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n",
            encoding="utf-8",
        )
    except Exception as exc:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                f"COMMAND: {' '.join(cmd)}\n\nERROR:\n{exc}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        raise PdfMergeError("Falha ao aplicar OCR") from exc
