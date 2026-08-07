"""Crée un utilisateur admin. Usage :
    python -m scripts.create_admin --username dino --full-name "Dino" --role admin
Le mot de passe est demandé de façon masquée (jamais en argument, jamais loggé).
"""
import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.database.session import async_session_factory
from app.core.security import hash_password
from app.models.user import User


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--role", default="admin", choices=["admin", "magazinier"])
    args = parser.parse_args()

    password = getpass.getpass("Mot de passe : ")
    confirm = getpass.getpass("Confirmer : ")
    if password != confirm:
        print("❌ Les mots de passe ne correspondent pas.")
        return
    if len(password) < 8:
        print("❌ Le mot de passe doit faire au moins 8 caractères.")
        return

    async with async_session_factory() as session:
        exists = await session.scalar(
            select(User).where(User.username == args.username)
        )
        if exists is not None:
            print(f"❌ L'utilisateur « {args.username} » existe déjà.")
            return
        user = User(
            username=args.username.strip(),
            full_name=args.full_name,
            password_hash=hash_password(password),
            role=args.role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"✅ Utilisateur « {args.username} » créé (rôle : {args.role}).")


if __name__ == "__main__":
    asyncio.run(main())