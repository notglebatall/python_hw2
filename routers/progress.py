import aiohttp
import os

from dotenv import load_dotenv

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from datetime import date

from database.models import User, WaterLog, FoodLog, WorkoutLog, DailyStats
from database.utils import get_or_create_daily_stats

load_dotenv()

progress_router = Router()


class FoodState(StatesGroup):
    waiting_for_amount = State()


# Словарь MET значений для разных типов тренировок
WORKOUT_METS = {
    'бег': 8.3,
    'ходьба': 3.5,
    'плавание': 5.8,
    'велосипед': 5.8,
    'йога': 2.5,
    'силовая': 3.5,
    'hiit': 8.0,
    'танцы': 4.5,
    'футбол': 7.0,
    'баскетбол': 6.5,
    'теннис': 7.3,
    'скакалка': 12.3,
    'эллипсоид': 5.0,
}

EMOJIS = {
        'бег': '🏃‍♂️',
        'ходьба': '🚶',
        'плавание': '🏊',
        'велосипед': '🚴',
        'йога': '🧘',
        'силовая': '💪',
        'hiit': '🔥',
        'танцы': '💃',
        'футбол': '⚽',
        'баскетбол': '🏀',
        'теннис': '🎾',
        'скакалка': '🪢',
        'эллипсоид': '🏋️',
    }


@progress_router.message(Command('log_water'))
async def log_water(message: Message, session: AsyncSession):
    """Логирование выпитой воды"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer('❌ Используйте: /log_water [количество в мл]\nПример: /log_water 250')
        return
    
    try:
        amount = int(args[1])
        if amount <= 0 or amount > 5000:
            await message.answer('❌ Пожалуйста, введите корректное количество (1-5000 мл)')
            return
    except ValueError:
        await message.answer('❌ Пожалуйста, введите число')
        return
    
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer('❌ Сначала настройте профиль командой /set_profile')
        return
    
    # Создаем запись
    water_log = WaterLog(
        user_id=user.id,
        amount=amount,
        log_date=date.today()
    )
    session.add(water_log)
    
    # Обновляем дневную статистику
    stats = await get_or_create_daily_stats(session, user.id, date.today())
    stats.total_water += amount # pyright: ignore[reportAttributeAccessIssue]
    
    await session.commit()
    
    # Рассчитываем прогресс
    remaining = stats.water_goal - stats.total_water
    progress_percent = min(100, int((stats.total_water / stats.water_goal) * 100))
    
    response = (
        f"💧 <b>Вода записана: {amount} мл</b>\n\n"
        f"📊 Прогресс за сегодня:\n"
        f"• Выпито: {stats.total_water} мл из {stats.water_goal} мл\n"
        f"• Прогресс: {progress_percent}%\n"
    )
    
    if remaining > 0:
        response += f"• Осталось: {remaining} мл 💪"
    else:
        response += f"• ✅ Цель достигнута! 🎉"
    
    await message.answer(response, parse_mode='HTML')


@progress_router.message(Command('log_food'))
async def log_food(message: Message, state: FSMContext, session: AsyncSession):
    """Логирование еды через OpenFoodFacts API"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer('❌ Используйте: /log_food [название продукта]\nПример: /log_food банан')
        return
    
    food_name = args[1].strip()
    
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer('❌ Сначала настройте профиль командой /set_profile')
        return
    
    waiting_message = await message.answer('🔍 Ищу продукт, пожалуйста, подождите...')
    
    # Поиск продукта через OpenFoodFacts API
    try:
        async with aiohttp.ClientSession() as http_session:
            url = f"https://world.openfoodfacts.org/cgi/search.pl"
            params = {
                'search_terms': food_name,
                'search_simple': 1,
                'action': 'process',
                'json': 1,
                'page_size': 1,
                'fields': 'product_name,nutriments'
            }
            
            async with http_session.get(url, params=params) as response:
                data = await response.json()
                
                if not data.get('products'):
                    await message.answer(f'❌ Продукт "{food_name}" не найден. Попробуйте другое название.')
                    return
                
                product = data['products'][0]
                product_name = product.get('product_name', food_name)
                nutriments = product.get('nutriments', {})
                
                # Безопасное преобразование в float
                calories_per_100g = float(nutriments.get('energy-kcal_100g') or nutriments.get('energy_100g') or 0)
                protein = float(nutriments.get('proteins_100g') or 0)
                fat = float(nutriments.get('fat_100g') or 0)
                carbs = float(nutriments.get('carbohydrates_100g') or 0)
                
                if calories_per_100g == 0:
                    await message.answer(f'❌ Не удалось получить данные о калорийности для "{product_name}"')
                    return
                
                # Сохраняем данные в FSM для следующего шага
                await state.update_data(
                    food_name=product_name,
                    calories_per_100g=calories_per_100g,
                    protein=protein,
                    fat=fat,
                    carbs=carbs,
                    user_id=user.id
                )
                await state.set_state(FoodState.waiting_for_amount)

                waiting_message.delete()
                
                emoji = '🍌' if 'банан' in product_name.lower() else '🍽'
                await message.answer(
                    f"{emoji} <b>{product_name}</b>\n\n"
                    f"📊 На 100 г:\n"
                    f"• Калории: {calories_per_100g:.1f} ккал\n"
                    f"• Белки: {protein:.1f} г\n"
                    f"• Жиры: {fat:.1f} г\n"
                    f"• Углеводы: {carbs:.1f} г\n\n"
                    f"❓ Сколько грамм вы съели?",
                    parse_mode='HTML'
                )
                
    except Exception as e:
        print(e)
        await message.answer(f'❌ Ошибка при поиске продукта: {str(e)}')



@progress_router.message(FoodState.waiting_for_amount)
async def process_food_amount(message: Message, state: FSMContext, session: AsyncSession):
    """Обработка количества съеденной еды"""
    try:
        amount = float(message.text)
        if amount <= 0 or amount > 10000:
            await message.answer('❌ Пожалуйста, введите корректное количество (1-10000 г)')
            return
    except ValueError:
        await message.answer('❌ Пожалуйста, введите число')
        return
    
    data = await state.get_data()
    
    # Рассчитываем БЖУ и калории
    calories = (data['calories_per_100g'] * amount) / 100
    protein = (data['protein'] * amount) / 100
    fat = (data['fat'] * amount) / 100
    carbs = (data['carbs'] * amount) / 100
    
    # Создаем запись о еде
    food_log = FoodLog(
        user_id=data['user_id'],
        food_name=data['food_name'],
        calories=calories,
        amount=amount,
        protein=protein,
        fat=fat,
        carbs=carbs,
        log_date=date.today()
    )
    session.add(food_log)
    
    # Обновляем дневную статистику
    stats = await get_or_create_daily_stats(session, data['user_id'], date.today())
    stats.total_calories += calories
    stats.total_protein += protein
    stats.total_fat += fat
    stats.total_carbs += carbs
    
    await session.commit()
    await state.clear()
    
    # Формируем ответ
    remaining_calories = stats.calorie_goal - stats.total_calories
    progress_percent = min(100, int((stats.total_calories / stats.calorie_goal) * 100))
    
    response = (
        f"✅ <b>Записано: {amount:.0f} г {data['food_name']}</b>\n\n"
        f"📊 Получено:\n"
        f"• Калории: {calories:.1f} ккал\n"
        f"• Белки: {protein:.1f} г\n"
        f"• Жиры: {fat:.1f} г\n"
        f"• Углеводы: {carbs:.1f} г\n\n"
        f"🔥 Прогресс за сегодня:\n"
        f"• Потреблено: {stats.total_calories:.0f} ккал из {stats.calorie_goal} ккал\n"
        f"• Прогресс: {progress_percent}%\n"
    )
    
    if remaining_calories > 0:
        response += f"• Осталось: {remaining_calories:.0f} ккал"
    else:
        response += f"• ⚠️ Цель превышена на {abs(remaining_calories):.0f} ккал"
    
    await message.answer(response, parse_mode='HTML')


@progress_router.message(Command('log_workout'))
async def log_workout(message: Message, session: AsyncSession):
    """Логирование тренировки"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        workout_list = ', '.join(WORKOUT_METS.keys())
        await message.answer(
            f'❌ Используйте: /log_workout [тип] [минуты]\n\n'
            f'Доступные типы тренировок:\n{workout_list}\n\n'
            f'Пример: /log_workout бег 30'
        )
        return
    
    workout_type = args[1].lower()
    
    try:
        duration = int(args[2])
        if duration <= 0 or duration > 600:
            await message.answer('❌ Длительность должна быть от 1 до 600 минут')
            return
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное количество минут')
        return
    
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer('❌ Сначала настройте профиль командой /set_profile')
        return
    
    # Определяем MET значение
    met = WORKOUT_METS.get(workout_type)
    if not met:
        workout_list = ', '.join(WORKOUT_METS.keys())
        await message.answer(f'❌ Неизвестный тип тренировки. Доступные: {workout_list}')
        return
    

    calories_burned = met * user.weight * (duration / 60)
    water_needed = int((duration / 30) * 200)
    
    # Создаем запись о тренировке
    workout_log = WorkoutLog(
        user_id=user.id,
        workout_type=workout_type,
        duration=duration,
        calories_burned=calories_burned,
        water_needed=water_needed,
        log_date=date.today()
    )
    session.add(workout_log)
    
    # Обновляем дневную статистику
    stats = await get_or_create_daily_stats(session, user.id, date.today())
    stats.burned_calories += calories_burned
    stats.water_goal += water_needed
    
    await session.commit()

    emoji = EMOJIS.get(workout_type, '💪')
    
    response = (
        f"{emoji} <b>Тренировка записана!</b>\n\n"
        f"📊 Детали:\n"
        f"• Тип: {workout_type.capitalize()}\n"
        f"• Длительность: {duration} мин\n"
        f"• Сожжено калорий: {calories_burned:.0f} ккал\n"
        f"• Интенсивность: {met} MET\n\n"
        f"💧 Дополнительная норма воды: +{water_needed} мл\n"
        f"Не забудьте пить воду! 🚰"
    )
    
    await message.answer(response, parse_mode='HTML')


@progress_router.message(Command('check_progress'))
async def check_progress(message: Message, session: AsyncSession):
    """Показать прогресс за сегодня"""
    result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer('❌ Сначала настройте профиль командой /set_profile')
        return
    
    stats = await get_or_create_daily_stats(session, user.id, date.today())

    water_percent = min(100, int((stats.total_water / stats.water_goal) * 100)) if stats.water_goal > 0 else 0
    calorie_percent = min(100, int((stats.total_calories / stats.calorie_goal) * 100)) if stats.calorie_goal > 0 else 0
    
    calorie_balance = stats.total_calories - stats.burned_calories
    
    response = (
        f"📊 <b>Ваш прогресс за сегодня</b>\n\n"
        f"💧 <b>Вода:</b>\n"
        f"• Выпито: {stats.total_water} мл из {stats.water_goal} мл\n"
        f"• Прогресс: {water_percent}%\n"
        f"• Осталось: {max(0, stats.water_goal - stats.total_water)} мл\n\n"
        
        f"🔥 <b>Калории:</b>\n"
        f"• Потреблено: {stats.total_calories:.0f} ккал из {stats.calorie_goal} ккал\n"
        f"• Сожжено: {stats.burned_calories:.0f} ккал\n"
        f"• Баланс: {calorie_balance:.0f} ккал\n"
        f"• Прогресс: {calorie_percent}%\n\n"
        
        f"🍽 <b>БЖУ:</b>\n"
        f"• Белки: {stats.total_protein:.1f} г\n"
        f"• Жиры: {stats.total_fat:.1f} г\n"
        f"• Углеводы: {stats.total_carbs:.1f} г\n"
    )
    
    await message.answer(response, parse_mode='HTML')
