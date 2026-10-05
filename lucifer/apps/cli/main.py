"""Local task submission and inspection CLI."""

import argparse
import json
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from lucifer.config.settings import Settings
from lucifer.core.tasks import TaskCreate
from lucifer.storage.database import SqlTaskRepository, make_engine


def main() -> int:
    parser = argparse.ArgumentParser(prog="lucifer-core")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health")
    create = commands.add_parser("create")
    create.add_argument("objective")
    show = commands.add_parser("show")
    show.add_argument("task_id", type=UUID)
    args = parser.parse_args()

    engine = make_engine(Settings.load().database_path)
    try:
        repository = SqlTaskRepository(sessionmaker(engine, expire_on_commit=False))
        if args.command == "health":
            result = {"status": "ok"}
        elif args.command == "create":
            result = repository.create(TaskCreate(objective=args.objective)).model_dump(mode="json")
        else:
            task = repository.get(args.task_id)
            if task is None:
                parser.error("Task not found")
            result = task.model_dump(mode="json")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
