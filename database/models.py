from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.engine import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    
    weight = Column(Float, nullable=True)
    height = Column(Integer, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    activity_minutes = Column(Integer, default=0)
    city = Column(String, nullable=True)
    
    water_goal = Column(Integer, nullable=True)
    calorie_goal = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    water_logs = relationship("WaterLog", back_populates="user", cascade="all, delete-orphan")
    food_logs = relationship("FoodLog", back_populates="user", cascade="all, delete-orphan")
    workout_logs = relationship("WorkoutLog", back_populates="user", cascade="all, delete-orphan")
    daily_stats = relationship("DailyStats", back_populates="user", cascade="all, delete-orphan")


class WaterLog(Base):
    __tablename__ = "water_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    amount = Column(Integer, nullable=False)

    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    log_date = Column(Date, server_default=func.current_date(), index=True)
    
    user = relationship("User", back_populates="water_logs")


class FoodLog(Base):
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    food_name = Column(String, nullable=False)
    calories = Column(Float, nullable=False)
    amount = Column(Float, nullable=True)
    protein = Column(Float, nullable=True)
    fat = Column(Float, nullable=True)
    carbs = Column(Float, nullable=True)

    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    log_date = Column(Date, server_default=func.current_date(), index=True)
    
    user = relationship("User", back_populates="food_logs")


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    workout_type = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)
    calories_burned = Column(Float, nullable=False)
    water_needed = Column(Integer, default=0)

    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    log_date = Column(Date, server_default=func.current_date(), index=True)
    
    user = relationship("User", back_populates="workout_logs")


class DailyStats(Base):
    """Модель ежедневной статистики пользователя"""
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stat_date = Column(Date, nullable=False, index=True)
    
    # Вода
    total_water = Column(Integer, default=0)
    water_goal = Column(Integer, default=0)
    
    # Калории
    total_calories = Column(Float, default=0)
    burned_calories = Column(Float, default=0)
    calorie_goal = Column(Integer, default=0)
    
    # БЖУ
    total_protein = Column(Float, default=0)
    total_fat = Column(Float, default=0)
    total_carbs = Column(Float, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="daily_stats")
