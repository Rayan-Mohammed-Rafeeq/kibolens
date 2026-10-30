from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import engine


def database_is_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
