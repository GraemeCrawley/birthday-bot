from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from decimal import Decimal


class GiftIdeaBase(BaseModel):
    idea: str
    price: Optional[Decimal] = None
    url: Optional[str] = None


class GiftIdeaCreate(GiftIdeaBase):
    pass


class GiftIdeaUpdate(BaseModel):
    idea: Optional[str] = None
    purchased: Optional[bool] = None
    price: Optional[Decimal] = None
    url: Optional[str] = None


class GiftIdea(GiftIdeaBase):
    id: int
    person_id: int
    purchased: bool
    purchased_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PersonBase(BaseModel):
    name: str
    birthday: date
    notes: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    birthday: Optional[date] = None
    notes: Optional[str] = None


class Person(PersonBase):
    id: int
    created_at: datetime
    gifts: List[GiftIdea] = []

    class Config:
        from_attributes = True


class PersonWithCountdown(Person):
    days_until: int
    age_turning: Optional[int] = None


class SettingsUpdate(BaseModel):
    notification_email: Optional[str] = None
    # Comma-separated list of days-before-birthday that trigger an alert
    # (exact match per day; e.g. "60,30,7,0"). Empty/invalid tokens dropped silently.
    notify_thresholds: Optional[str] = Field(None, max_length=200)


class Settings(BaseModel):
    notification_email: Optional[str] = None
    notify_thresholds: str = "60,30,7,0"
    push_enabled: bool = False


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushSubscriptionResponse(BaseModel):
    id: int
    endpoint: str
    created_at: datetime

    class Config:
        from_attributes = True
