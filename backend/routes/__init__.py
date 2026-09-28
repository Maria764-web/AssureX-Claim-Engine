"""
AssureX Routes Package
Registers all modular domain blueprints on the Flask application.
"""

from flask import Flask
from backend.routes.main_routes import main_bp
from backend.routes.auth_routes import auth_bp
from backend.routes.claim_routes import claim_bp
from backend.routes.product_routes import product_bp
from backend.routes.warranty_routes import warranty_bp
from backend.routes.document_routes import document_bp
from backend.routes.repair_routes import repair_bp
from backend.routes.prediction_routes import prediction_bp
from backend.routes.notification_routes import notification_bp
from backend.routes.reviewer_routes import reviewer_bp
from backend.routes.service_center_routes import service_center_bp
from backend.routes.admin_routes import admin_bp
from backend.routes.report_routes import report_bp
from backend.routes.ocr_routes import ocr_bp


def register_blueprints(app: Flask) -> None:
    """Register all modular application blueprints."""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(claim_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(warranty_bp)
    app.register_blueprint(document_bp)
    app.register_blueprint(repair_bp)
    app.register_blueprint(prediction_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(reviewer_bp)
    app.register_blueprint(service_center_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(ocr_bp)


__all__ = ["register_blueprints"]
