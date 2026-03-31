import os
from pathlib import Path
from flask import Flask


def create_app():
    # Adicionar Tesseract ao PATH para OCR funcionar
    tesseract_path = r"C:\Program Files\Tesseract-OCR"
    if os.path.exists(tesseract_path):
        os.environ["PATH"] = tesseract_path + os.pathsep + os.environ.get("PATH", "")

    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB total per request
    app.config["TMP_ROOT"] = str(Path(__file__).resolve().parent.parent / "tmp")
    app.config["MAX_FILE_SIZE"] = 30 * 1024 * 1024  # 30MB per file
    app.config["CLEANUP_TTL_HOURS"] = 24
    app.config["OCR_ENABLED"] = True
    app.config["OCR_LANGS"] = "por"

    Path(app.config["TMP_ROOT"]).mkdir(parents=True, exist_ok=True)

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
