"""
Tests for campaign service logic.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from services import campaign_service


def test_get_target_for_today_ramps_over_weeks():
    campaign = {"daily_target": 100, "ramp_weeks": 10, "current_week": 5}
    target = campaign_service.get_target_for_today(campaign)
    assert target == 50  # 100 * 5/10


def test_get_target_for_today_capped_at_max_weeks():
    campaign = {"daily_target": 100, "ramp_weeks": 10, "current_week": 20}
    target = campaign_service.get_target_for_today(campaign)
    assert target == 100


def test_is_active_hour_uses_timezone():
    # Pick a timezone where we know the current UTC hour maps differently
    tz_name = "Pacific/Auckland"
    now_utc = datetime.utcnow()
    now_nz = datetime.now(ZoneInfo(tz_name))
    hour_nz = now_nz.hour

    campaign = {
        "active_start": hour_nz,
        "active_end": (hour_nz + 1) % 24,
        "timezone": tz_name,
    }
    assert campaign_service.is_active_hour(campaign) is True


def test_is_active_hour_outside_window():
    hour = (datetime.utcnow().hour + 6) % 24
    campaign = {
        "active_start": hour,
        "active_end": (hour + 1) % 24,
        "timezone": "UTC",
    }
    assert campaign_service.is_active_hour(campaign) is False


def test_advance_campaign_weeks(test_db):
    # Create a sender account first (FK)
    from services import account_service
    sender_id = account_service.create_account("sender@test.local", "app-password-16", "sender")
    campaign_id = campaign_service.create_campaign({
        "name": "Test Campaign",
        "domain_name": "test.local",
        "sender_account_id": sender_id,
        "template_id": None,
        "peer_account_ids": [],
        "daily_target": 10,
        "ramp_weeks": 4,
        "tick_interval": 5,
        "active_start": 9,
        "active_end": 17,
        "timezone": "UTC",
        "current_week": 1,
    })
    campaign_service.advance_campaign_weeks()
    camp = campaign_service.get_campaign(campaign_id)
    assert camp["current_week"] == 2
