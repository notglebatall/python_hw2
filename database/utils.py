import os
import aiohttp

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import User, DailyStats

from datetime import date

from dotenv import load_dotenv

load_dotenv()

async def create_or_update_user(
    session: AsyncSession,
    telegram_id: int,
    username: str,
    weight: float,
    height: int,
    age: int,
    activity_minutes: int,
    city: str,
    water_goal: int,
    calorie_goal: int
) -> User:
    """Создает нового пользователя или обновляет существующего"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        user.weight = weight
        user.height = height
        user.age = age
        user.activity_minutes = activity_minutes
        user.city = city
        user.water_goal = water_goal
        user.calorie_goal = calorie_goal
        user.username = username
    else:
        user = User(
            telegram_id=telegram_id,
            username=username,
            weight=weight,
            height=height,
            age=age,
            activity_minutes=activity_minutes,
            city=city,
            water_goal=water_goal,
            calorie_goal=calorie_goal
        )
        session.add(user)
    
    await session.commit()
    return user


async def get_or_create_daily_stats(session: AsyncSession, user_id: int, stat_date: date) -> DailyStats:
    """Получить или создать статистику за день"""
    result = await session.execute(
        select(DailyStats).where(
            DailyStats.user_id == user_id,
            DailyStats.stat_date == stat_date
        )
    )
    stats = result.scalar_one_or_none()
    
    if not stats:
        # Получаем цели пользователя
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        stats = DailyStats(
            user_id=user_id,
            stat_date=stat_date,
            water_goal=user.water_goal or 0,
            calorie_goal=user.calorie_goal or 0
        )
        session.add(stats)
        await session.commit()
        await session.refresh(stats)
    
    return stats


async def get_temperature(city: str) -> float:
    """
    Получает текущую температуру в городе через OpenWeatherMap API.
    
    Args:
        city: Название города
        
    Returns:
        Температура в градусах Цельсия или 20.0 по умолчанию при ошибке
    """
    api_key = os.getenv('OPENWEATHER_API_KEY')
    
    if not api_key:
        return 20.0
    
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather'
        params = {
            'q': city,
            'units': 'metric',
            'lang': 'ru',
            'appid': api_key
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return round(data['main']['temp'], 1)
                else:
                    return 20.0
    except Exception:
        return 20.0

async def calculate_norms(weight: float, height: float, age: int, 
                         active_minutes: int, city: str) -> dict:
    """
    Рассчитывает дневные нормы воды и калорий на основе параметров пользователя.
    
    Args:
        weight: Вес в кг
        height: Рост в см
        age: Возраст
        active_minutes: Минуты активности в день
        city: Город для определения температуры
        
    Returns:
        Словарь с нормами воды, калорий и дополнительной информацией
    """
    # Получаем температуру
    temperature = await get_temperature(city)
    
    # Расчет нормы воды
    base_water = weight * 30 / 1000  # базовая норма в литрах
    activity_water = (active_minutes / 30) * 0.5  # за активность
    
    # Дополнительная вода за жаркую погоду
    weather_water = 0
    if temperature > 25:
        if temperature > 30:
            weather_water = 1.0  # 1 литр при очень жаркой погоде
        else:
            weather_water = 0.5  # 0.5 литра при умеренно жаркой погоде
    
    total_water = round(base_water + activity_water + weather_water, 2)
    
    # Расчет нормы калорий (формула Миффлина-Сан Жеора для мужчин)
    bmr = 10 * weight + 6.25 * height - 5 * age + 5
    
    # Коэффициент активности на основе минут активности
    if active_minutes == 0:
        activity_factor = 1.2
        activity_level = "минимальный"
    elif active_minutes < 30:
        activity_factor = 1.375
        activity_level = "низкий"
    elif active_minutes < 60:
        activity_factor = 1.55
        activity_level = "умеренный"
    elif active_minutes < 90:
        activity_factor = 1.725
        activity_level = "высокий"
    else:
        activity_factor = 1.9
        activity_level = "очень высокий"
    
    total_calories = int(bmr * activity_factor)
    activity_bonus = int(total_calories - bmr)
    
    return {
        'total_water': total_water,
        'base_water': base_water,
        'activity_water': activity_water,
        'weather_water': weather_water,
        'total_calories': total_calories,
        'bmr': int(bmr),
        'activity_factor': activity_factor,
        'activity_bonus': activity_bonus,
        'activity_level': activity_level,
        'temperature': temperature
    }
