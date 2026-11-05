from flask import Flask, send_from_directory

from . import api, bot, db
from .config import ROOT, Config


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    app.json.ensure_ascii = False  # keep Khmer and other scripts readable
    app.config["APP"] = config or Config.from_env()
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    if app.config["APP"].dev_mode:
        app.logger.warning("DEV_MODE is on: anyone can sign in as anyone. Never use it on a public server.")

    db.init_db(app.config["APP"].db_path)
    app.teardown_appcontext(db.close_db)
    app.register_blueprint(api.bp)
    app.register_blueprint(bot.bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
