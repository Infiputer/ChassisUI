import os

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chassis_user:randomsecurepassword45219@localhost/chassis_ui"
)