import argparse
import asyncio

from app.agents.graph import multi_agent_system
from app.core.config import get_settings


async def run(question: str) -> None:
    settings = get_settings()
    result = await multi_agent_system.run(
        question=question,
        schema_name=settings.db_schema,
        history=[],
        system_prompt=settings.bot_system_prompt,
        force_data=True,
    )
    print("Q     :", question)
    print("SQL   :", result.sql)
    print("Rows  :", result.row_count)
    print("Answer:", result.answer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask one database question without the React UI.")
    parser.add_argument("question", nargs="+", help="Natural-language database question")
    args = parser.parse_args()
    asyncio.run(run(" ".join(args.question)))


if __name__ == "__main__":
    main()
