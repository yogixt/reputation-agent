"""
Template API routes
"""

from fastapi import APIRouter, Depends, Request
import auth
import models
from config import settings
from limiter import limiter
from services import template_service
from templates import emails

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[models.TemplateOut])
async def list_templates(session: dict = Depends(auth.require_auth)):
    return template_service.list_templates()


@router.post("", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def create_template(req: models.TemplateCreate, request: Request, session: dict = Depends(auth.require_auth)):
    tid = template_service.create_template(req.name, req.subject_template, req.body_template, req.reply_template, req.variables_json)
    return {"success": True, "id": tid}


@router.post("/preview")
@limiter.limit(settings.default_rate_limit)
async def preview_template(req: models.TemplatePreviewRequest, request: Request, session: dict = Depends(auth.require_auth)):
    vars_list = emails.parse_variables(req.variables_json or "[]")
    vars_dict = emails.generate_variables()
    for v in vars_list:
        if v not in vars_dict:
            vars_dict[v] = f"[{v}]"
    subject, body = emails.render_email(req.subject_template, req.body_template, vars_dict)
    reply = emails.render_reply(req.reply_template, vars_dict)
    return {"subject": subject, "body": body, "reply": reply, "variables": vars_dict}


@router.delete("/{template_id}")
@limiter.limit(settings.default_rate_limit)
async def delete_template(template_id: int, request: Request, session: dict = Depends(auth.require_auth)):
    template_service.delete_template(template_id)
    return {"success": True}


@router.patch("/{template_id}")
@limiter.limit(settings.default_rate_limit)
async def update_template(template_id: int, req: models.TemplateCreate, request: Request, session: dict = Depends(auth.require_auth)):
    template_service.update_template(template_id, req.model_dump())
    return {"success": True}
