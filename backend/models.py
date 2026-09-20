from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

def gen_uuid():
    return str(uuid.uuid4())

def gen_key():
    import secrets
    return secrets.token_urlsafe(24)

class User(db.Model):
    __tablename__ = "users"
    id            = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    username      = db.Column(db.String(32), unique=True, nullable=False)
    email         = db.Column(db.String(128), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    tracking_consent_at = db.Column(db.DateTime, nullable=True)
    tracking_consent_version = db.Column(db.String(32), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    memberships   = db.relationship("ProjectMember", back_populates="user", cascade="all, delete")
    sessions      = db.relationship("Session", back_populates="user", cascade="all, delete")
    subscription  = db.relationship("AccountSubscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    account_payments = db.relationship("AccountPayment", back_populates="user", cascade="all, delete")

    @property
    def account_plan(self):
        if not self.subscription:
            return "free"
        if self.subscription.expires_at and self.subscription.expires_at < datetime.utcnow():
            return "free"
        return self.subscription.plan

    @property
    def account_plan_expires_at(self):
        if self.account_plan == "free":
            return None
        return self.subscription.expires_at

class Project(db.Model):
    __tablename__ = "projects"
    id                 = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    owner_id           = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name               = db.Column(db.String(32), nullable=False)
    project_key        = db.Column(db.String(64), unique=True, default=gen_key)
    plan               = db.Column(db.String(16), default="free")   # free / pro / studio
    plan_expires_at    = db.Column(db.DateTime, nullable=True)
    plan_activated_by  = db.Column(db.String(16), nullable=True)    # paypal / robux / manual
    plan_note          = db.Column(db.Text, nullable=True)
    key_regenerated_at = db.Column(db.DateTime, nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    owner      = db.relationship("User", foreign_keys=[owner_id])
    members    = db.relationship("ProjectMember", back_populates="project", cascade="all, delete")
    sessions   = db.relationship("Session", back_populates="project", cascade="all, delete")
    task_columns = db.relationship("TaskColumn", back_populates="project", cascade="all, delete-orphan", order_by="TaskColumn.position")
    tasks      = db.relationship("Task", back_populates="project", cascade="all, delete")
    documents  = db.relationship("ProjectDocument", back_populates="project", cascade="all, delete")

    @property
    def effective_plan(self):
        return self.owner.account_plan

    @property
    def history_days(self):
        if self.effective_plan == "studio": return None   # unlimited
        if self.effective_plan == "pro":    return 60
        return 7                                # free

    @property
    def max_members(self):
        if self.effective_plan == "studio": return None
        if self.effective_plan == "pro":    return 15
        return 5

    @property
    def max_co_admins(self):
        if self.effective_plan == "studio": return None
        if self.effective_plan == "pro":    return 1
        return 0

class ProjectMember(db.Model):
    __tablename__ = "project_members"
    id         = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    user_id    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    role       = db.Column(db.String(16), default="member")   # owner / co_admin / member
    joined_at  = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", back_populates="members")
    user    = db.relationship("User", back_populates="memberships")

class Session(db.Model):
    __tablename__ = "sessions"
    id         = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    user_id    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at   = db.Column(db.DateTime, nullable=True)

    project       = db.relationship("Project", back_populates="sessions")
    user          = db.relationship("User", back_populates="sessions")
    script_events = db.relationship("ScriptEvent", back_populates="session", cascade="all, delete")
    instance_events = db.relationship("InstanceEvent", back_populates="session", cascade="all, delete")

    @property
    def duration_seconds(self):
        if not self.ended_at:
            return int((datetime.utcnow() - self.started_at).total_seconds())
        return int((self.ended_at - self.started_at).total_seconds())

class ScriptEvent(db.Model):
    __tablename__ = "script_events"
    id            = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    session_id    = db.Column(db.String(36), db.ForeignKey("sessions.id"), nullable=False)
    script_name   = db.Column(db.String(256), nullable=False)
    event_type    = db.Column(db.String(16), nullable=False)  # open / close
    chars_added   = db.Column(db.Integer, default=0)
    chars_removed = db.Column(db.Integer, default=0)
    occurred_at   = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship("Session", back_populates="script_events")

class InstanceEvent(db.Model):
    __tablename__ = "instance_events"
    id            = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    session_id    = db.Column(db.String(36), db.ForeignKey("sessions.id"), nullable=False)
    category      = db.Column(db.String(16), nullable=False)  # part / ui
    action        = db.Column(db.String(16), nullable=False)  # added / removed
    class_name    = db.Column(db.String(64), nullable=False)
    instance_name = db.Column(db.String(256), nullable=False)
    count         = db.Column(db.Integer, default=1)
    occurred_at   = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship("Session", back_populates="instance_events")

class TaskColumn(db.Model):
    __tablename__ = "task_columns"
    id         = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False, index=True)
    name       = db.Column(db.String(32), nullable=False)
    position   = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="task_columns")
    tasks = db.relationship("Task", back_populates="column")


class Task(db.Model):
    __tablename__ = "tasks"
    id             = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id     = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    created_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    column_id     = db.Column(db.String(36), db.ForeignKey("task_columns.id"), nullable=True, index=True)
    position      = db.Column(db.Integer, default=0, nullable=False)
    title          = db.Column(db.String(32), nullable=False)
    description_md = db.Column(db.Text, default="")
    due_at         = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="tasks")
    column = db.relationship("TaskColumn", back_populates="tasks")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    assignments = db.relationship("TaskAssignment", back_populates="task", cascade="all, delete-orphan")


class TaskAssignment(db.Model):
    __tablename__ = "task_assignments"
    task_id      = db.Column(db.String(36), db.ForeignKey("tasks.id"), primary_key=True)
    user_id      = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True)
    completed    = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    task = db.relationship("Task", back_populates="assignments")
    user = db.relationship("User")


class ProjectDocument(db.Model):
    __tablename__ = "project_documents"
    id            = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id    = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    updated_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    title         = db.Column(db.String(32), nullable=False)
    content_md    = db.Column(db.Text, default="")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="documents")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])


class AccountApiKey(db.Model):
    __tablename__ = "account_api_keys"
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True)
    key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    key_prefix = db.Column(db.String(12), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    regenerated_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


class AccountSubscription(db.Model):
    __tablename__ = "account_subscriptions"
    user_id       = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True)
    plan          = db.Column(db.String(16), default="free", nullable=False)
    expires_at    = db.Column(db.DateTime, nullable=True)
    activated_by  = db.Column(db.String(16), nullable=True)
    note          = db.Column(db.Text, nullable=True)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="subscription")


class AccountPayment(db.Model):
    __tablename__ = "account_payments"
    id         = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    plan       = db.Column(db.String(16), nullable=False)
    duration   = db.Column(db.Integer, nullable=False)
    method     = db.Column(db.String(16), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    status     = db.Column(db.String(16), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="account_payments")


class UpgradeCode(db.Model):
    __tablename__ = "upgrade_codes"
    id             = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    code_hash      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    code_prefix    = db.Column(db.String(8), nullable=False)
    plan           = db.Column(db.String(16), nullable=False)
    duration_days  = db.Column(db.Integer, nullable=False)
    expires_at     = db.Column(db.DateTime, nullable=True)
    created_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    redeemed_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    redeemed_at    = db.Column(db.DateTime, nullable=True)
    revoked_at     = db.Column(db.DateTime, nullable=True)
    note           = db.Column(db.Text, default="")

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    redeemed_by = db.relationship("User", foreign_keys=[redeemed_by_id])

    @property
    def status(self):
        if self.revoked_at:
            return "revoked"
        if self.redeemed_at:
            return "redeemed"
        if self.expires_at and self.expires_at < datetime.utcnow():
            return "expired"
        return "unused"


class Payment(db.Model):
    __tablename__ = "payments"
    id          = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    project_id  = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    plan        = db.Column(db.String(16), nullable=False)
    duration    = db.Column(db.Integer, nullable=False)  # months
    method      = db.Column(db.String(16), nullable=False)  # dummy / paypal / robux
    amount      = db.Column(db.Float, nullable=False)
    status      = db.Column(db.String(16), default="pending")  # pending / completed / failed
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
