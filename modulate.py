"""The Modulate client.

Submits a script to a machine-type worker group, optionally waits for the
result, and can look the result up again later by job id.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

from resonate.resonate import Resonate

# The name `worker.py` registers `execute` under. The client never imports the
# worker: it invokes the function by name, on whichever worker group it targets.
EXECUTE = "execute"


async def get_by_id(resonate: Resonate, job_id: str) -> str | None:
    """Return the job's result, or None if it has not resolved yet."""
    record = await resonate.promises.get(job_id)
    if record.state == "resolved":
        return record.value.data if record.value else None
    return None


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Execute a Python script remotely.")
    parser.add_argument(
        "-m",
        "--machine",
        dest="machine_type",
        help="Machine type to execute on. Must match a running worker's group.",
        default="gpu",
    )
    parser.add_argument(
        "-i", "--id", dest="id", help="Sets an id, defaults to a random uuid."
    )
    parser.add_argument(
        "-w",
        "--no-wait",
        dest="wait",
        action="store_false",
        help="Return as soon as the job is submitted, instead of waiting for it.",
    )
    parser.add_argument("--get", dest="get_id", action="store", help="Which id to get")
    return parser.parse_known_args()


async def main() -> None:
    args, argv = parse_args()

    resonate = Resonate(url=os.environ.get("RESONATE_URL", "http://localhost:8001"))

    # Yield once so the SDK's background network task is running before the
    # first call. Without it the first awaited call can lose the race with
    # startup and fail with "network has been stopped".
    await asyncio.sleep(0)

    try:
        if args.get_id is not None:
            res = await get_by_id(resonate, args.get_id)
            if res:
                print(f"Job results located at: {res}")
            else:
                print(f"Job {args.get_id} is not ready yet.")
            return

        job_id = args.id if args.id is not None else str(uuid.uuid4())

        if len(argv) < 1:
            print("Script name is required")
            raise SystemExit(1)

        try:
            with open(argv[0], "r") as file:
                content = file.read()
        except FileNotFoundError:
            print(f"Error: File not found: {argv[0]}")
            raise

        print(f"You can retrieve this execution using {job_id}")
        print(f"Will execute {argv[0]} in {args.machine_type}...")

        # The caller picks the root promise id, so `--get <id>` can find this
        # execution again later. Everything from here on is durable: the job
        # survives this process exiting, crashing, or being restarted.
        handle = resonate.options(target=args.machine_type).rpc(
            job_id, EXECUTE, content, job_id
        )

        if args.wait:
            result = await handle.result()
            print(f"results are located at {result}")
        else:
            # Awaiting the id waits for the promise to be created on the
            # server, so the job is durably recorded before we exit.
            await handle.id()
            print(f"Submitted. Check on it with: --get {job_id}")
    finally:
        await resonate.stop()


if __name__ == "__main__":
    asyncio.run(main())
