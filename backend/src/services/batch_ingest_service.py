from typing import Any

from sqlalchemy.orm import Session

from src.schemas.conversation import ConversationCreateSchema
from src.services.conversation_service import validate_conversation, upsert_conversation

DEFAULT_CHUNK_SIZE = 50


def ingest_batch(
    db: Session,
    conversations: list[dict[str, Any]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, int | list[dict[str, Any]]]:
    ingested = 0
    failed = 0
    errors: list[dict[str, Any]] = []

    for i in range(0, len(conversations), chunk_size):
        chunk = conversations[i : i + chunk_size]
        for idx, conv_data in enumerate(chunk):
            try:
                validated = validate_conversation(conv_data)
                upsert_conversation(db, validated)
                ingested += 1
            except Exception as e:
                failed += 1
                errors.append(
                    {
                        "index": i + idx,
                        "conversation_id": conv_data.get("conversation_id", "?"),
                        "error": str(e),
                    }
                )

    return {"ingested": ingested, "failed": failed, "errors": errors}
