"""Shared persistence and continuation flow for Leader requirement answers."""
from typing import AsyncGenerator, Dict, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from leader.langgraph_entry import async_continue_leader_workflow
from models import LeaderSession, Message
from utils.error_handler import safe_sse_error


def create_question_answer_events(
    db_session: Session,
    session: LeaderSession,
    answers: Iterable[str],
    config: dict,
    user_id: int,
) -> AsyncGenerator[Dict, None]:
    """Persist one answer round and return the shared continuation event stream."""
    answer_list = [str(answer) for answer in answers]
    latest_question_msg = db_session.query(Message).filter(
        Message.leader_session_id == session.id,
        Message.message_type == 'question',
    ).order_by(Message.sequence_number.desc()).first()

    questions = []
    if latest_question_msg and isinstance(latest_question_msg.content, dict):
        questions = latest_question_msg.content.get('questions', []) or []

    max_seq_subq = db_session.query(func.max(Message.sequence_number)).filter(
        Message.leader_session_id == session.id,
        Message.sequence_number.isnot(None),
    ).scalar_subquery()
    last_seq_msg = db_session.query(Message).filter(
        Message.leader_session_id == session.id,
        Message.sequence_number == max_seq_subq,
    ).with_for_update(nowait=True).first()
    next_seq = (last_seq_msg.sequence_number + 1) if last_seq_msg else 1

    answer_data = []
    for index, answer in enumerate(answer_list):
        question_text = ''
        if index < len(questions):
            question = questions[index]
            question_text = question.get('question', '') if isinstance(question, dict) else str(question)
        answer_data.append({'question': question_text, 'answer': answer})

    db_session.add(Message.create_leader_message(
        conversation_id=session.conversation_id,
        leader_session_id=session.id,
        message_type='answer',
        content={'questions': questions, 'answers': answer_data},
        sequence_number=next_seq,
    ))
    db_session.commit()

    async def event_generator() -> AsyncGenerator[Dict, None]:
        try:
            async for event in async_continue_leader_workflow(
                session_id=session.id,
                answers=answer_list,
                config=config,
                user_id=user_id,
            ):
                yield event
        except Exception as error:
            yield safe_sse_error(error, "回答问题后恢复失败")

    return event_generator()
