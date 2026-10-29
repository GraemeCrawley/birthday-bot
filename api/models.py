from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from database import Base


class Person(Base):
    __tablename__ = "birthday_people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    birthday = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    gifts = relationship("GiftIdea", back_populates="person", cascade="all, delete-orphan")


class GiftIdea(Base):
    __tablename__ = "birthday_gift_ideas"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("birthday_people.id"), nullable=False)
    idea = Column(String(500), nullable=False)
    purchased = Column(Boolean, default=False)
    purchased_at = Column(DateTime, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    url = Column(String(1000), nullable=True)
    # Soft-delete: set the day after a birthday for purchased gifts (carries the
    # current cycle to a close). Unpurchased gifts are not auto-archived. Anything
    # with archived_at != NULL is hidden from the bot and web app default views
    # but kept in the DB for year-over-year history.
    archived_at = Column(DateTime, nullable=True, index=True)

    person = relationship("Person", back_populates="gifts")


class Setting(Base):
    __tablename__ = "birthday_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)


class PushSubscription(Base):
    __tablename__ = "birthday_push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(Text, unique=True, nullable=False)
    p256dh_key = Column(String(255), nullable=False)
    auth_key = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
