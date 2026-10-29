from typing import Optional
from sqlalchemy.orm import Session

from models import Setting


def get_setting(db: Session, key: str) -> Optional[str]:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else None


def set_setting(db: Session, key: str, value: str):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
    db.commit()
