from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import User
from database.utils import create_or_update_user, calculate_norms

profile_router = Router()


class ProfileState(StatesGroup):
    weight = State()
    height = State()
    age = State()
    active_minutes = State()
    city = State()


@profile_router.message(Command('set_profile'))
async def set_profile(message: Message, state: FSMContext):
    await state.set_state(ProfileState.weight)
    await message.answer('Введите ваш вес (в кг):')


@profile_router.message(ProfileState.weight)
async def set_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        if weight <= 0 or weight > 300:
            await message.answer('Пожалуйста, введите корректный вес:')
            return
        
        await state.update_data(weight=weight)
        await state.set_state(ProfileState.height)
        await message.answer('Введите ваш рост (в см):')
    except ValueError:
        await message.answer('Пожалуйста, введите число.')


@profile_router.message(ProfileState.height)
async def set_height(message: Message, state: FSMContext):
    try:
        height = float(message.text)
        if height <= 0 or height > 250:
            await message.answer('Пожалуйста, введите корректный рост')
            return
        
        await state.update_data(height=height)
        await state.set_state(ProfileState.age)
        await message.answer('Введите ваш возраст:')
    except ValueError:
        await message.answer('Пожалуйста, введите число.')


@profile_router.message(ProfileState.age)
async def set_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age <= 0 or age > 120:
            await message.answer('Пожалуйста, введите корректный возраст:')
            return
        
        await state.update_data(age=age)
        await state.set_state(ProfileState.active_minutes)
        await message.answer('Сколько минут активности у вас в день?')
    except ValueError:
        await message.answer('Пожалуйста, введите целое число.')


@profile_router.message(ProfileState.active_minutes)
async def set_active_minutes(message: Message, state: FSMContext):
    try:
        active_minutes = int(message.text)
        if active_minutes < 0 or active_minutes > 1440:
            await message.answer('Пожалуйста, введите корректное количество минут:')
            return
        
        await state.update_data(active_minutes=active_minutes)
        await state.set_state(ProfileState.city)
        await message.answer('В каком городе вы находитесь?')
    except ValueError:
        await message.answer('Пожалуйста, введите целое число.')


@profile_router.message(ProfileState.city)
async def set_city(message: Message, state: FSMContext, session: AsyncSession):
    city = message.text.strip()
    
    if not city or len(city) < 2:
        await message.answer('Пожалуйста, введите корректное название города:')
        return
    
    await state.update_data(city=city)
    
    data = await state.get_data()
    
    norms = await calculate_norms(
        weight=data['weight'],
        height=data['height'],
        age=data['age'],
        active_minutes=data['active_minutes'],
        city=city
    )
    
    await state.update_data(
        target_calories=norms['total_calories'],
        water_norm=norms['total_water']
    )
    
    await create_or_update_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        weight=data['weight'],
        height=int(data['height']),
        age=data['age'],
        activity_minutes=data['active_minutes'],
        city=city,
        water_goal=int(norms['total_water'] * 1000),
        calorie_goal=norms['total_calories']
    )
    
    # Формируем сообщение о норме воды с учетом погоды
    water_breakdown = (
        f"💧 <b>Норма воды: {norms['total_water']} л/день</b>\n"
        f"├ Базовая норма: {round(norms['base_water'], 2)} л ({data['weight']} кг × 30 мл)\n"
        f"├ За активность: +{round(norms['activity_water'], 2)} л\n"
    )
    
    if norms['weather_water'] > 0:
        water_breakdown += f"├ За жаркую погоду ({norms['temperature']}°C): +{norms['weather_water']} л\n"
    else:
        water_breakdown += f"├ Погода ({norms['temperature']}°C): без корректировки\n"
    
    profile_summary = (
        f"✅ <b>Ваш профиль успешно настроен!</b>\n\n"
        f"📊 <b>Данные профиля:</b>\n"
        f"• Вес: {data['weight']} кг\n"
        f"• Рост: {data['height']} см\n"
        f"• Возраст: {data['age']} лет\n"
        f"• Активность: {data['active_minutes']} минут/день ({norms['activity_level']} уровень)\n"
        f"• Город: {data['city']}\n\n"
        
        f"{water_breakdown}\n"
        
        f"🔥 <b>Норма калорий: {norms['total_calories']} ккал/день</b>\n"
        f"├ Базовый метаболизм: {norms['bmr']} ккал\n"
        f"├ Коэффициент активности: ×{norms['activity_factor']}\n"
        f"└ Бонус за активность: +{norms['activity_bonus']} ккал\n\n"
        
        f"💡 <i>Используйте команды для отслеживания вашего прогресса!</i>"
    )
    
    await message.answer(profile_summary, parse_mode='HTML')
    await state.clear()

