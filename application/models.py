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
    

    
    