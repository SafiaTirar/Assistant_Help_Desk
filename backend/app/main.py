from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.admin_dashboard import router as admin_dashboard_router
from app.api.admin_fallbacks import router as admin_fallbacks_router
from app.api.admin_documents import router as admin_documents_router
from app.api.admin_evaluations import router as admin_evaluations_router
from app.api.admin_contacts import router as admin_contacts_router
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI(title="Onboarding Assistant API", version="0.1.0")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(admin_dashboard_router, prefix="/api")
app.include_router(admin_fallbacks_router, prefix="/api")
app.include_router(admin_documents_router, prefix="/api")
app.include_router(admin_evaluations_router, prefix="/api")
app.include_router(admin_contacts_router, prefix="/api")
