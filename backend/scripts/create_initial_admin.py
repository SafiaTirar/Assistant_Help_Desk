import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from pydantic import EmailStr, TypeAdapter

from app.core import env  # noqa: F401
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.user import User


def main() -> None:
    email = str(TypeAdapter(EmailStr).validate_python(
        os.environ["INITIAL_ADMIN_EMAIL"].lower()
    ))
    password = os.environ["INITIAL_ADMIN_PASSWORD"]
    name = os.getenv("INITIAL_ADMIN_NAME", "Administrateur").strip()
    if len(password) < 12 or not all((
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
    )):
        raise ValueError(
            "INITIAL_ADMIN_PASSWORD doit contenir au moins 12 caractères, "
            "une minuscule, une majuscule et un chiffre."
        )
    if not name:
        raise ValueError("INITIAL_ADMIN_NAME ne peut pas être vide.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            print(f"Compte administrateur déjà présent : {email}")
            return
        admin = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role="ADMIN",
            status="Actif",
            must_change_password=True,
        )
        db.add(admin)
        db.commit()
        print(f"Compte administrateur créé : {email}")


if __name__ == "__main__":
    main()
