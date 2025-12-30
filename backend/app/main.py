from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.core.config import settings
from app.api.endpoints import reconciliation, tax_analysis, tax



app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0")

@app.on_event("startup")
async def startup_event():
    from app.db.session import engine
    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ou ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(reconciliation.router, prefix="/api/v1/recon", tags=["Reconciliation"])
app.include_router(tax_analysis.router, prefix="/api/v1", tags=["Tax Analysis"])
app.include_router(tax.router, prefix="/api/v1/tax", tags=["Tax Reports"])

@app.get("/")
async def root():
    return {"message": "Finance Recon AI Backend is running"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "config": {
            "db_configured": bool(settings.DATABASE_URL),
            "ollama_url": settings.OLLAMA_BASE_URL
        }
    }
