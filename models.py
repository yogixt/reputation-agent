"""
Pydantic request/response models
"""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator, model_validator


# ─── Auth ───
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    success: bool
    email: str


# ─── Accounts ───
class AccountCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(None)
    role: str = Field(..., pattern="^(sender|peer)$")
    provider: str

    @model_validator(mode="after")
    def _sender_requires_password(self):
        if self.role == "sender" and not self.password:
            raise ValueError("sender accounts require an app password")
        return self


class BulkAccountItem(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(None)
    role: str = Field(..., pattern="^(sender|peer)$")
    provider: Optional[str] = "gmail"

    @model_validator(mode="after")
    def _sender_requires_password(self):
        if self.role == "sender" and not self.password:
            raise ValueError("sender accounts require an app password")
        return self


class BulkAccountImport(BaseModel):
    accounts: List[BulkAccountItem]


class WarmupSetupRequest(BaseModel):
    sender_app_password: Optional[str] = Field(None)
    daily_target: int = Field(5, ge=1, le=500)
    ramp_weeks: int = Field(12, ge=1, le=52)
    tick_interval: int = Field(5, ge=1, le=60)
    active_start: int = Field(9, ge=0, le=23)
    active_end: int = Field(20, ge=0, le=23)
    timezone: str = Field("UTC", pattern="^(?:UTC|[A-Za-z_]+/[A-Za-z_]+)$")
    tick_now: bool = True
    overwrite_passwords: bool = False


class AccountUpdate(BaseModel):
    status: Optional[str] = None
    password: Optional[str] = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    provider: str
    status: str
    health_score: int
    fail_count: int
    last_check: Optional[str]
    last_error: Optional[str]
    created_at: Optional[str]


# ─── Templates ───
class TemplateCreate(BaseModel):
    name: str
    subject_template: str
    body_template: str
    reply_template: Optional[str] = None
    variables_json: Optional[str] = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    subject_template: str
    body_template: str
    reply_template: Optional[str]
    variables_json: Optional[str]
    is_default: int
    created_at: Optional[str]


class TemplatePreviewRequest(BaseModel):
    subject_template: str
    body_template: str
    reply_template: Optional[str] = None
    variables_json: Optional[str] = None


# ─── Campaigns ───
class CampaignCreate(BaseModel):
    name: str
    domain_name: str
    sender_account_id: int
    template_id: int
    peer_account_ids: List[int]
    daily_target: int = Field(..., ge=1, le=500)
    ramp_weeks: int = Field(..., ge=1, le=52)
    tick_interval: int = Field(..., ge=1, le=60)
    active_start: int = Field(..., ge=0, le=23)
    active_end: int = Field(..., ge=0, le=23)
    timezone: str = Field(..., pattern="^(?:UTC|[A-Za-z_]+/[A-Za-z_]+)$")


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    domain_name: Optional[str] = None
    sender_account_id: Optional[int] = None
    daily_target: Optional[int] = None
    ramp_weeks: Optional[int] = None
    tick_interval: Optional[int] = None
    active_start: Optional[int] = None
    active_end: Optional[int] = None
    timezone: Optional[str] = Field(None, pattern="^(?:UTC|[A-Za-z_]+/[A-Za-z_]+)$")
    peer_account_ids: Optional[List[int]] = None
    template_id: Optional[int] = None
    current_week: Optional[int] = Field(None, ge=1, le=52)


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    domain_name: str
    sender_account_id: int
    sender_email: Optional[str]
    template_id: Optional[int]
    template_name: Optional[str]
    status: str
    daily_target: int
    ramp_weeks: int
    current_week: int
    tick_interval: int
    active_start: int
    active_end: int
    created_at: Optional[str]
    updated_at: Optional[str]
    peer_count: int


# ─── Queue / Sends ───
class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    campaign_id: int
    campaign_name: Optional[str]
    from_email: Optional[str]
    to_email: Optional[str]
    subject: str
    status: str
    retry_count: int
    error: Optional[str]
    scheduled_at: Optional[str]
    sent_at: Optional[str]
    created_at: Optional[str]


# ─── Reputation ───
class ReputationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    campaign_id: int
    date: str
    sent: int
    moved: int
    opened: int
    replied: int
    score: float
    inbox_rate: float
    spam_rate: float


# ─── Stats ───
class StatsOut(BaseModel):
    campaigns: int
    accounts: int
    senders: int
    peers: int
    pending: int
    sent: int
    opened: int
    replied: int
    moved: int
    avg_score: float


# ─── Logs ───
class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: str
    source: Optional[str]
    message: str
    created_at: str


# ─── Settings ───
class SettingsUpdate(BaseModel):
    tick_interval_minutes: Optional[int] = None
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    move_probability: Optional[float] = None
    open_probability: Optional[float] = None
    reply_probability: Optional[float] = None
