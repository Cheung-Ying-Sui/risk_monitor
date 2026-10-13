import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import get_authenticated_user
from api.routes.tracking import router as tracking_router
from api.routes.vessels import router as vessels_router
from api.routes.sanctions import router as sanctions_router
from api.routes.navigation import router as navigation_router, insurance_prediction_router
from api.routes.risk_zones import router as risk_zones_router
from api.routes.insurance import router as insurance_router
from api.routes.port_weather import router as port_weather_router
from 情报收集模块.ukmto.api import router as ukmto_router


DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        ",".join(DEFAULT_ALLOWED_ORIGINS),
    ).split(",")
    if origin.strip()
]
ALLOWED_ORIGIN_REGEX = os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or None


app = FastAPI(
    title="Risk Monitor API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_DEPENDENCIES = [Depends(get_authenticated_user)]

app.include_router(vessels_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(tracking_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(sanctions_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(navigation_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(insurance_prediction_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(risk_zones_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(insurance_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(port_weather_router, dependencies=AUTH_DEPENDENCIES)
app.include_router(ukmto_router, dependencies=AUTH_DEPENDENCIES)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
