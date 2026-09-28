"""
AssureX Error Handling Module
Provides application-level error handlers for 400, 401, 403, 404, 413, and 500 errors.
Ensures internal stack traces are never exposed in production-style responses.
"""

from flask import Flask, jsonify, render_template, request


def register_error_handlers(app: Flask) -> None:
    """Register custom HTTP error handlers on the Flask application."""

    def is_api_request() -> bool:
        """Determine if current request expects JSON response."""
        return (
            request.is_json
            or request.path.startswith("/api/")
            or request.path.startswith("/health")
            or request.accept_mimetypes.best == "application/json"
        )

    @app.errorhandler(400)
    def bad_request_error(error):
        message = getattr(error, "description", "Bad Request")
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Bad Request",
                "message": message,
                "status_code": 400
            }), 400
        return render_error_html("400 - Bad Request", message, 400)

    @app.errorhandler(401)
    def unauthorized_error(error):
        message = getattr(error, "description", "Authentication required to access this resource.")
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Unauthorized",
                "message": message,
                "status_code": 401
            }), 401
        return render_error_html("401 - Unauthorized", message, 401)

    @app.errorhandler(403)
    def forbidden_error(error):
        message = getattr(error, "description", "You do not have permission to access this resource.")
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": message,
                "status_code": 403
            }), 403
        return render_error_html("403 - Forbidden", message, 403)

    @app.errorhandler(404)
    def not_found_error(error):
        message = getattr(error, "description", "The requested resource could not be found.")
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": message,
                "status_code": 404
            }), 404
        return render_error_html("404 - Not Found", message, 404)

    @app.errorhandler(413)
    def payload_too_large_error(error):
        message = "File size exceeds the maximum allowed upload limit (16MB)."
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Payload Too Large",
                "message": message,
                "status_code": 413
            }), 413
        return render_error_html("413 - File Too Large", message, 413)

    @app.errorhandler(500)
    def internal_server_error(error):
        # Log error securely in app logger
        app.logger.error(f"Internal Server Error: {str(error)}")
        message = "An unexpected internal server error occurred. Please try again later."
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Internal Server Error",
                "message": message,
                "status_code": 500
            }), 500
        return render_error_html("500 - Server Error", message, 500)


def render_error_html(title: str, message: str, status_code: int):
    """Fallback HTML error response if templates are not yet fully styled."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title} - AssureX</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            padding: 2.5rem;
            border-radius: 1rem;
            max-width: 480px;
            text-align: center;
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5);
        }}
        h1 {{ color: #38bdf8; margin-top: 0; font-size: 1.75rem; }}
        p {{ color: #94a3b8; line-height: 1.6; margin-bottom: 1.5rem; }}
        a {{
            display: inline-block;
            background: #0284c7;
            color: white;
            padding: 0.6rem 1.25rem;
            border-radius: 0.5rem;
            text-decoration: none;
            font-weight: 500;
        }}
        a:hover {{ background: #0369a1; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{title}</h1>
        <p>{message}</p>
        <a href="/">Return to Home</a>
    </div>
</body>
</html>"""
    return html, status_code
