#!/usr/bin/env python3
"""
CLI utility to provision or reset photographer credentials for EventFrame.
Usage:
    python scripts/create_photographer.py --email admin@eventframe.local --password secret --name "Lead Photographer"
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth.security import hash_password
from backend.models.database import SessionLocal, init_db
from backend.models.entities import User

def main():
    parser = argparse.ArgumentParser(description="Create or update photographer credentials.")
    parser.add_argument("--email", required=True, help="Photographer email address")
    parser.add_argument("--password", required=True, help="Photographer password")
    parser.add_argument("--name", default="Photographer", help="Photographer display name")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if user:
            user.hashed_password = hash_password(args.password)
            user.full_name = args.name
            user.is_active = True
            db.commit()
            print(f"[✓] Successfully updated credentials for existing user: {user.email}")
        else:
            new_user = User(
                email=args.email,
                hashed_password=hash_password(args.password),
                full_name=args.name,
                is_active=True
            )
            db.add(new_user)
            db.commit()
            print(f"[✓] Successfully created photographer user: {new_user.email} (ID: {new_user.id})")
    except Exception as e:
        db.rollback()
        print(f"[✗] Error creating photographer: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
