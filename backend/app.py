"""
AssureX Claim Engine - Application Entry Point & Factory
Initializes Flask app, extensions, models, routes, and security configurations.
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
from flask import Flask, jsonify, redirect, request, url_for, flash
from backend.config.config import config_by_name, BASE_DIR
from backend.extensions import db, migrate, login_manager, csrf
from backend.models import (
    User,
    Product,
    Warranty,
    Claim,
    Document,
    RepairHistory,
    Prediction,
    RuleResult,
    Notification,
    AuditLog,
    ModelVersion,
    DocumentExtraction
)
from backend.routes import register_blueprints
from backend.utils.error_handler import register_error_handlers
from backend.utils.helpers import is_api_request
from backend.utils.security import ROLE_ADMIN


def create_app(config_name: str = None) -> Flask:
    """
    Application factory for AssureX Claim Engine.

    Args:
        config_name: 'development', 'testing', 'production', or None (reads from env)

    Returns:
        Configured Flask application instance
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development").lower()

    app_config = config_by_name.get(config_name, config_by_name["default"])

    # Initialize Flask app pointing to frontend templates/assets
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "frontend" / "pages"),
        static_folder=str(BASE_DIR / "frontend"),
        static_url_path="/static"
    )

    # Load configuration
    app.config.from_object(app_config)

    # Ensure upload directory exists
    upload_path = Path(app.config["UPLOAD_FOLDER"])
    upload_path.mkdir(parents=True, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrations_dir = str(BASE_DIR / "database" / "migrations")
    migrate.init_app(app, db, directory=migrations_dir)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Configure Flask-Login user loader
    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    # Configure unauthorized handler for API / Web split
    @login_manager.unauthorized_handler
    def unauthorized_callback():
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Unauthorized",
                "message": "Authentication required."
            }), 401
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("auth.login_view", next=request.url))

    # Register blueprints and error handlers
    register_blueprints(app)
    register_error_handlers(app)

    # Exempt pure API blueprints from CSRF token enforcement to support programmatic JSON calls
    from backend.routes.main_routes import main_bp
    from backend.routes.auth_routes import auth_bp
    from backend.routes.claim_routes import claim_bp
    from backend.routes.product_routes import product_bp
    from backend.routes.warranty_routes import warranty_bp
    from backend.routes.document_routes import document_bp
    from backend.routes.repair_routes import repair_bp
    from backend.routes.prediction_routes import prediction_bp
    from backend.routes.notification_routes import notification_bp
    from backend.routes.report_routes import report_bp
    from backend.routes.admin_routes import admin_bp
    from backend.routes.ocr_routes import ocr_bp
    from backend.routes.reviewer_routes import reviewer_bp
    from backend.routes.service_center_routes import service_center_bp

    csrf.exempt(main_bp)
    csrf.exempt(auth_bp)
    csrf.exempt(claim_bp)
    csrf.exempt(product_bp)
    csrf.exempt(warranty_bp)
    csrf.exempt(document_bp)
    csrf.exempt(repair_bp)
    csrf.exempt(prediction_bp)
    csrf.exempt(notification_bp)
    csrf.exempt(report_bp)
    csrf.exempt(admin_bp)
    csrf.exempt(ocr_bp)
    csrf.exempt(reviewer_bp)
    csrf.exempt(service_center_bp)

    # Register CLI Commands
    @app.cli.command("init-db")
    def init_db_command():
        """Initialize and create all database tables in SQLite (assurex.db)."""
        with app.app_context():
            db.create_all()
            try:
                from database.migrate_step5a import run_all_migrations
                run_all_migrations()
            except Exception as e:
                click.echo(f"Migration note: {e}")
            click.echo("Successfully initialized all AssureX database tables.")

    @app.cli.command("migrate-db")
    def migrate_db_command():
        """Run safe schema migrations for any existing SQLite databases."""
        from database.migrate_step5a import run_all_migrations
        run_all_migrations()

    @app.cli.command("create-admin")
    @click.option("--name", default="System Administrator", help="Admin Full Name")
    @click.option("--email", prompt=True, help="Admin Email Address")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Admin Password")
    def create_admin_command(name, email, password):
        """CLI tool for authorized creation of the initial root Administrator account."""
        with app.app_context():
            existing = User.query.filter_by(email=email.lower().strip()).first()
            if existing:
                click.echo(f"Error: User with email {email} already exists.")
                return
            admin = User(
                name=name,
                email=email.lower().strip(),
                password=password,
                role=ROLE_ADMIN,
                is_active=True
            )
            db.session.add(admin)
            db.session.commit()
            click.echo(f"Administrator {email} (UID: {admin.user_uid}) created successfully.")

    # Shell context for flask shell
    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "User": User,
            "Product": Product,
            "Warranty": Warranty,
            "Claim": Claim,
            "Document": Document,
            "RepairHistory": RepairHistory,
            "Prediction": Prediction,
            "RuleResult": RuleResult,
            "Notification": Notification,
            "AuditLog": AuditLog,
            "ModelVersion": ModelVersion
        }

    return app


# Default app instance for WSGI / CLI
app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", port=5000, debug=True)
