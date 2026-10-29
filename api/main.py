import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import List
from zoneinfo import ZoneInfo

# Match scheduler.calculate_days_until: date math runs in the bot owner's
# local tz (TZ env var, UTC if unset) so the dashboard agrees with the bot.
LOCAL_TZ = ZoneInfo(os.getenv("TZ") or "UTC")

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import Person, GiftIdea, Setting, PushSubscription
from schemas import (
    PersonCreate, PersonUpdate, Person as PersonSchema, PersonWithCountdown,
    GiftIdeaCreate, GiftIdeaUpdate, GiftIdea as GiftIdeaSchema,
    SettingsUpdate, Settings,
    PushSubscriptionCreate, PushSubscriptionResponse
)

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
from auth import get_setting, set_setting
from scheduler import start_scheduler, calculate_days_until


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="Birthday Reminder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")



@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Liveness + database check, used by the Docker healthcheck."""
    db.query(Setting).first()
    return {"status": "ok"}


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse("static/service-worker.js", media_type="application/javascript")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/dashboard", response_model=List[PersonWithCountdown])
async def dashboard(db: Session = Depends(get_db)):
    people = db.query(Person).all()
    result = []
    for person in people:
        days_until = calculate_days_until(person.birthday)
        today = datetime.now(LOCAL_TZ).date()
        this_year_birthday = person.birthday.replace(year=today.year)
        if this_year_birthday < today:
            age_turning = today.year + 1 - person.birthday.year
        else:
            age_turning = today.year - person.birthday.year

        result.append(PersonWithCountdown(
            id=person.id,
            name=person.name,
            birthday=person.birthday,
            notes=person.notes,
            created_at=person.created_at,
            gifts=[GiftIdeaSchema.model_validate(g) for g in person.gifts if g.archived_at is None],
            days_until=days_until,
            age_turning=age_turning
        ))

    return sorted(result, key=lambda x: x.days_until)


@app.get("/api/people", response_model=List[PersonSchema])
async def list_people(db: Session = Depends(get_db)):
    return db.query(Person).order_by(Person.name).all()


@app.post("/api/people", response_model=PersonSchema)
async def create_person(data: PersonCreate, db: Session = Depends(get_db)):
    person = Person(**data.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@app.get("/api/people/{person_id}", response_model=PersonSchema)
async def get_person(person_id: int, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@app.put("/api/people/{person_id}", response_model=PersonSchema)
async def update_person(person_id: int, data: PersonUpdate, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(person, key, value)

    db.commit()
    db.refresh(person)
    return person


@app.delete("/api/people/{person_id}")
async def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    db.delete(person)
    db.commit()
    return {"success": True}


@app.get("/api/people/{person_id}/gifts", response_model=List[GiftIdeaSchema])
async def list_gifts(person_id: int, db: Session = Depends(get_db), include_archived: bool = False):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if include_archived:
        return person.gifts
    return [g for g in person.gifts if g.archived_at is None]


@app.post("/api/people/{person_id}/gifts", response_model=GiftIdeaSchema)
async def create_gift(person_id: int, data: GiftIdeaCreate, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    gift = GiftIdea(person_id=person_id, **data.model_dump())
    db.add(gift)
    db.commit()
    db.refresh(gift)
    return gift


@app.put("/api/gifts/{gift_id}", response_model=GiftIdeaSchema)
async def update_gift(gift_id: int, data: GiftIdeaUpdate, db: Session = Depends(get_db)):
    gift = db.query(GiftIdea).filter(GiftIdea.id == gift_id).first()
    if not gift:
        raise HTTPException(status_code=404, detail="Gift idea not found")

    update_data = data.model_dump(exclude_unset=True)

    if "purchased" in update_data:
        if update_data["purchased"] and not gift.purchased:
            update_data["purchased_at"] = datetime.utcnow()
        elif not update_data["purchased"]:
            update_data["purchased_at"] = None

    for key, value in update_data.items():
        setattr(gift, key, value)

    db.commit()
    db.refresh(gift)
    return gift


@app.delete("/api/gifts/{gift_id}")
async def delete_gift(gift_id: int, db: Session = Depends(get_db)):
    gift = db.query(GiftIdea).filter(GiftIdea.id == gift_id).first()
    if not gift:
        raise HTTPException(status_code=404, detail="Gift idea not found")

    db.delete(gift)
    db.commit()
    return {"success": True}


@app.post("/api/people/{person_id}/reset-gift-cycle")
async def reset_gift_cycle(person_id: int, db: Session = Depends(get_db)):
    """Close out the current gift cycle for a person.

    Soft-archives every PURCHASED gift (sets archived_at). Unpurchased ideas
    are left in place — they remain as candidates for next year. This is
    intended to be called once, the day after each birthday, by the
    birthday-bot scheduler. Idempotent: running twice on the same day is a no-op
    on already-archived rows.
    """
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    archived_count = 0
    now = datetime.utcnow()
    for gift in person.gifts:
        if gift.purchased and gift.archived_at is None:
            gift.archived_at = now
            archived_count += 1
    db.commit()
    return {"archived_count": archived_count}


@app.get("/api/settings", response_model=Settings)
async def get_settings(db: Session = Depends(get_db)):
    return Settings(
        notification_email=get_setting(db, "notification_email"),
        notify_thresholds=get_setting(db, "notify_thresholds") or "60,30,7,0",
    )


@app.put("/api/settings")
async def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    if data.notification_email is not None:
        set_setting(db, "notification_email", data.notification_email)
    if data.notify_thresholds is not None:
        set_setting(db, "notify_thresholds", data.notify_thresholds)

    return {"success": True}


@app.get("/api/push/vapid-public-key")
async def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=500, detail="Push notifications not configured")
    return {"publicKey": VAPID_PUBLIC_KEY}


@app.post("/api/push/subscribe", response_model=PushSubscriptionResponse)
async def push_subscribe(data: PushSubscriptionCreate, db: Session = Depends(get_db)):
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == data.endpoint).first()
    if existing:
        existing.p256dh_key = data.keys.p256dh
        existing.auth_key = data.keys.auth
        db.commit()
        db.refresh(existing)
        return existing

    subscription = PushSubscription(
        endpoint=data.endpoint,
        p256dh_key=data.keys.p256dh,
        auth_key=data.keys.auth
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@app.post("/api/push/unsubscribe")
async def push_unsubscribe(data: PushSubscriptionCreate, db: Session = Depends(get_db)):
    subscription = db.query(PushSubscription).filter(PushSubscription.endpoint == data.endpoint).first()
    if subscription:
        db.delete(subscription)
        db.commit()
    return {"success": True}


@app.get("/api/push/status")
async def push_status(db: Session = Depends(get_db)):
    count = db.query(PushSubscription).count()
    return {
        "configured": bool(VAPID_PUBLIC_KEY),
        "subscriptions": count
    }


@app.post("/api/push/test")
async def push_test(db: Session = Depends(get_db)):
    from scheduler import send_push_notifications
    result = send_push_notifications(test=True)
    return {"success": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
