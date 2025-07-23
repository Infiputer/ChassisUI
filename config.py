import os

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://chassis_user:@localhost/chassis_ui")
)