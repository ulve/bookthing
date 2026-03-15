#!/usr/bin/env python3
"""
Generate a magic link for sharing audiobook access.

Usage:
    python scripts/genlink.py --label "for Alice"
    python scripts/genlink.py --label "shared" --multi-use --days 90
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import init_db
from app.auth import create_magic_link


def main():
    parser = argparse.ArgumentParser(description="Generate a magic access link")
    parser.add_argument("--label", required=True, help="Human note (e.g. 'for Alice')")
    parser.add_argument("--multi-use", action="store_true", help="Allow link to be used multiple times")
    parser.add_argument("--days", type=int, default=30, help="Days until link expires (default: 30)")
    parser.add_argument("--admin", action="store_true", help="Grant admin (metadata editing) access")
    args = parser.parse_args()

    init_db()
    url = create_magic_link(label=args.label, multi_use=args.multi_use, days=args.days, is_admin=args.admin)
    print(f"\nMagic link for '{args.label}':")
    print(f"  {url}\n")
    admin_note = " [ADMIN]" if args.admin else ""
    print(f"Expires in {args.days} days. Single-use: {not args.multi_use}{admin_note}")


if __name__ == "__main__":
    main()
