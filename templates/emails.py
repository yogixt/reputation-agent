"""
Email template rendering engine.

Templates are rendered in a sandboxed Jinja2 environment to prevent access to
Python internals while still supporting variables and simple filters.
"""

import json
import random
from datetime import datetime
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import UndefinedError


# Sandboxed environment: no arbitrary Python attribute access or unsafe filters.
_jinja_env = SandboxedEnvironment(autoescape=False)


def render_template(template_str: str, variables: dict = None) -> str:
    if not template_str:
        return ""
    try:
        tmpl = _jinja_env.from_string(template_str)
        ctx = variables or {}
        return tmpl.render(**ctx)
    except UndefinedError:
        # If variable missing, just return raw template
        return template_str
    except Exception:
        return template_str


def render_email(subject_template: str, body_template: str, variables: dict = None) -> tuple:
    subject = render_template(subject_template, variables)
    body = render_template(body_template, variables)
    return subject, body


def render_reply(reply_template: str, variables: dict = None) -> str:
    if not reply_template:
        return ""
    return render_template(reply_template, variables)


def parse_variables(variables_json: str) -> dict:
    if not variables_json:
        return {}
    try:
        return json.loads(variables_json)
    except Exception:
        return {}


def generate_variables(campaign_variables: dict = None) -> dict:
    """Build variables for warm-up emails from campaign-provided values."""
    variables = {}
    if campaign_variables:
        variables.update(campaign_variables)
    return variables
