from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters.state import State, StatesGroup

from database import async_session
from database.models import Incident, IncidentStatus
from services import zabbix_api, message_utils

router = Router()


class CommentState(StatesGroup):
    waiting_comment = State()


@router.callback_query(F.data.startswith("take:"))
async def take_incident(callback: CallbackQuery):
    event_id = callback.data.split(":")[1]
    user = callback.from_user

    async with async_session() as session:
        incident = await session.get(Incident, event_id)
        if incident.status == IncidentStatus.open:
            incident.status = IncidentStatus.in_progress
            incident.assigned_to = (
                f"@{user.username}" if user.username else user.full_name
            )
            await session.commit()

            await message_utils.update_incident_message(
                incident,
                buttons=[
                    [{"text": "Закрыть", "callback_data": f"close:{event_id}"}],
                    [{"text": "Отклонить", "callback_data": f"reject:{event_id}"}],
                ],
            )
            await callback.answer(f"Инцидент взят в работу!")


@router.callback_query(F.data.startswith(("close:", "reject:")))
async def handle_resolution(callback: CallbackQuery, state: FSMContext):
    action, event_id = callback.data.split(":")[:2]
    await state.update_data(action=action, event_id=event_id)
    await state.set_state(CommentState.waiting_comment)
    await callback.message.answer(
        f"Введите комментарий для {'закрытия' if action == 'close' else 'отклонения'}:",
        reply_to_message_id=callback.message.message_id,
    )


@router.message(CommentState.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data["action"]
    event_id = data["event_id"]
    comment = message.text

    async with async_session() as session:
        incident = await session.get(Incident, event_id)
        incident.status = (
            IncidentStatus.closed if action == "close" else IncidentStatus.rejected
        )
        incident.resolution_comment = comment
        await session.commit()

        # Close in Zabbix
        await zabbix_api.acknowledge_event(event_id, comment)

        # Update message
        await message_utils.update_incident_message(incident, remove_buttons=True)

    await state.clear()
