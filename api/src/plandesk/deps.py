"""Request-scoped dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from plandesk.ai.provider import AdaptationProvider
from plandesk.db import get_session
from plandesk.services.holidays import HolidayClient

Session = Annotated[AsyncSession, Depends(get_session)]


def _holiday_client(request: Request) -> HolidayClient:
    return request.app.state.holiday_client


def _provider(request: Request) -> AdaptationProvider:
    return request.app.state.ai_provider


def _current_user(request: Request) -> str:
    """Fixed demo planner; the app has no sign-in."""
    return request.app.state.settings.demo_user


Holidays = Annotated[HolidayClient, Depends(_holiday_client)]
Provider = Annotated[AdaptationProvider, Depends(_provider)]
CurrentUser = Annotated[str, Depends(_current_user)]
