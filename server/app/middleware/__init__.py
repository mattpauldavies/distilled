"""Request-scoped context resolution (tenant, repo).

Naming note: despite the package name, these are FastAPI dependencies
(injected per-route via Depends), not ASGI middleware — they run only for
routes that declare them, after routing. The actual HTTP middleware (CORS,
security headers, rate limiting) lives in app/main.py.
"""
