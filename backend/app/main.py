"""FastAPI application entrypoint.

    cd backend && .venv/bin/uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import auth_backend, fastapi_users, google_router
from app.routes import router
from app.schemas import UserCreate, UserRead, UserUpdate
from app.sync.router import router as sync_router

app = FastAPI(title="BG Real Estate Intelligence API", version="0.1.0")

# Vite dev server origin (frontend talks to the API in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(sync_router)

# --- auth (fastapi-users): login / register / reset / Google / current-user --
app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/api/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/auth", tags=["auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(), prefix="/api/auth", tags=["auth"]
)
app.include_router(google_router, prefix="/api/auth/google", tags=["auth"])
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/api/users", tags=["users"],
)


@app.get("/health")
def health():
    return {"status": "ok"}
