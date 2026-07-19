import argparse
import asyncio

from app.services.query_agent import query_agent


async def run(question: str) -> None:
    result = await query_agent.answer_data_question(question)
    print("Q     :", result.question)
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
