"""
DeliverIt API - Sistema de gestión de entregas y rutas
Desarrollado con FastAPI + SQL Server
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.modules.administration.controller import router as admin_router
# from src.modules.sellers.controller import router as sellers_router
# from src.modules.operators.controller import router as operator_router
from src.modules.staff.controller import router as staff_router
from src.modules.warehouses.controller import router as warehouses_router
from src.modules.customers.controller import router as customers_router
from src.modules.products.controller import router as products_router
from src.modules.orders.controller import router as orders_router
from src.modules.routes.controller import router as routes_router
from src.modules.routes.route_detail_controller import router as route_service_router
from src.modules.auth.jwt_routes import router as auth_router

# =========================================
# CONFIGURACIÓN DE LA APLICACIÓN
# =========================================

app = FastAPI(
    title="Bluetrack API",
    version="1.0.0",
    description="API REST para gestión de entregas, rutas y logística",
    docs_url="/docs",
    redoc_url="/redoc",

)

# =========================================
# MIDDLEWARE - CORS
# =========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # 🔑 Explícito
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Cookie",  # 🔑 IMPORTANTE para cookies
        "Set-Cookie",  # 🔑 IMPORTANTE para cookies
    ],
    expose_headers=["Set-Cookie"],  # 🔑 Expone Set-Cookie al frontend
    max_age=3600,  # Cache preflight requests por 1 hora
)

# =========================================
# MANEJO GLOBAL DE ERRORES
# =========================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Maneja errores de validación con mensajes amigables para el frontend.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Error de validación en los datos enviados",
            "errors": exc.errors(),
            "path": str(request.url)
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Captura errores no manejados para evitar exponer información sensible.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Error interno del servidor",
            "detail": str(exc) if app.debug else "Contacta al administrador"
        },
    )

# =========================================
# ROUTERS
# =========================================

app.include_router(auth_router)
app.include_router(admin_router)
app .include_router(staff_router)
app.include_router(warehouses_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(routes_router)
app.include_router(route_service_router)

# =========================================
# ENDPOINTS DE UTILIDAD
# =========================================

@app.get("/", tags=["Root"])
async def root():
    """
    Endpoint raíz - Información básica de la API.
    """
    return {
        "service": "DeliverIt API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check - Verifica que el servidor esté funcionando.
    Útil para monitoreo y pruebas de CI/CD.
    """
    return {
        "status": "healthy",
        "service": "DeliverIt API",
        "version": "1.0.0"
    }


@app.get("/api/info", tags=["Info"])
async def api_info():
    """
    Información detallada de la API para el frontend.
    """
    return {
        "name": "DeliverIt API",
        "version": "1.0.0",
        "description": "Sistema de gestión de entregas y rutas",
        "endpoints": {
            "auth": "/auth",
            "admin": "/admin",
            "sellers": "/sellers",
            "operators": "/operators",
            "warehouses": "/warehouses",
            "customers": "/customers",
            "products": "/products",
            "orders": "/orders",
            "routes": "/routes"
        }
    }

# =========================================
# EVENTOS DE CICLO DE VIDA
# =========================================

@app.on_event("startup")
async def startup_event():
    """
    Se ejecuta al iniciar el servidor.
    """
    print("🚀 DeliverIt API iniciada correctamente")
    print("📚 Documentación: http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Se ejecuta al cerrar el servidor.
    """
    print("👋 DeliverIt API detenida")
