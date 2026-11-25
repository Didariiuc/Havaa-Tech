from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from .db import Base
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(120))
    email: Mapped[str]=mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(20), default='buyer')
    vendor_name: Mapped[str|None]=mapped_column(String(140), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Product(Base):
    __tablename__='products'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(220), index=True)
    brand: Mapped[str]=mapped_column(String(100))
    model: Mapped[str]=mapped_column(String(180))
    category: Mapped[str]=mapped_column(String(40), index=True)
    specs: Mapped[str]=mapped_column(Text, default='{}')
    price_min: Mapped[float]=mapped_column(Float)
    price_max: Mapped[float]=mapped_column(Float)
    stock: Mapped[int]=mapped_column(Integer, default=10)
    vendor_id: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    image: Mapped[str]=mapped_column(String(500), default='')
    description: Mapped[str]=mapped_column(Text, default='')
    active: Mapped[bool]=mapped_column(Boolean, default=True)
class Order(Base):
    __tablename__='orders'
    id: Mapped[int]=mapped_column(primary_key=True)
    buyer_id: Mapped[int]=mapped_column(ForeignKey('users.id'), index=True)
    vendor_id: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    total: Mapped[float]=mapped_column(Float)
    status: Mapped[str]=mapped_column(String(40), default='processing')
    items_json: Mapped[str]=mapped_column(Text)
    delivered_at: Mapped[datetime|None]=mapped_column(DateTime, nullable=True)
    dispatched_at: Mapped[datetime|None]=mapped_column(DateTime, nullable=True)
    estimated_delivery_at: Mapped[datetime|None]=mapped_column(DateTime, nullable=True)
    courier_name: Mapped[str|None]=mapped_column(String(120), nullable=True)
    tracking_number: Mapped[str|None]=mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class ReturnCase(Base):
    __tablename__='return_cases'
    id: Mapped[int]=mapped_column(primary_key=True)
    order_id: Mapped[int]=mapped_column(ForeignKey('orders.id'), index=True)
    buyer_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    vendor_id: Mapped[int|None]=mapped_column(ForeignKey('users.id'), nullable=True)
    reason: Mapped[str]=mapped_column(Text)
    amount: Mapped[float]=mapped_column(Float)
    status: Mapped[str]=mapped_column(String(40), default='OPEN')
    policy_evidence: Mapped[str]=mapped_column(Text, default='')
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class ChatMessage(Base):
    __tablename__='chat_messages'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'), index=True)
    thread_id: Mapped[str]=mapped_column(String(100), index=True)
    role: Mapped[str]=mapped_column(String(20))
    content: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Preference(Base):
    __tablename__='preferences'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'), unique=True)
    language: Mapped[str]=mapped_column(String(20), default='bn')
    delivery_area: Mapped[str]=mapped_column(String(120), default='')
    refund_method: Mapped[str]=mapped_column(String(60), default='')
    consent: Mapped[bool]=mapped_column(Boolean, default=False)
