from datetime import datetime, timezone

from application import db


class User(db.Model):
    __tablename__="users"
    chat_id = db.Column(db.String(20), primary_key=True)
    groups = db.relationship("Group", back_populates="user")
    wallet = db.Column(db.Float)


class Group(db.Model):
    __tablename__="groups"
    chat_id = db.Column(db.String(20), primary_key=True)
    admin_id = db.Column(db.String(20), 
        db.ForeignKey("users.chat_id"))
    cost = db.Column(db.Float)
    members = db.relationship("Member", back_populates="group")
    profit = db.Column(db.Float)
    user = db.relationship("User", back_populates="groups")
    
class Member(db.Model):
    __tablename__="members"
    _id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.String(20))
    group_chat_id=db.Column(db.String(20), db.ForeignKey("groups.chat_id"))
    expiry = db.Column(db.String(20))
    group = db.relationship("Group", back_populates="members")
    

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idempotency_key = db.Column(db.String(36), unique=True, nullable=False)
    charge_code = db.Column(db.String(100), unique=True, nullable=True)
    user_chat_id = db.Column(
        db.String(20), db.ForeignKey("users.chat_id"), nullable=False
    )
    status = db.Column(db.String(20), nullable=False, default="pending")
    amount = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    