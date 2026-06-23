#!/usr/bin/env python3
"""
Create a warm-up email template from command-line arguments.

Usage:
    python scripts/create_template.py "Template Name" "subject" "body" "reply" '["var1", "var2"]'
"""

import sys

from services import template_service


def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/create_template.py <name> <subject> <body> [reply] [variables_json]")
        sys.exit(1)

    name = sys.argv[1]
    subject = sys.argv[2]
    body = sys.argv[3]
    reply = sys.argv[4] if len(sys.argv) > 4 else None
    variables = sys.argv[5] if len(sys.argv) > 5 else "[]"

    template_id = template_service.create_template(name, subject, body, reply, variables)
    print(f"Template created with ID: {template_id}")


if __name__ == "__main__":
    main()
