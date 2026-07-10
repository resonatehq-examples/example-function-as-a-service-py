"""Modulate — CLI for submitting scripts to a Resonate FaaS worker.

Usage:
    # Submit a script and wait for the result:
    uv run python modulate.py --id task-001 hello.py

    # Submit without waiting (fire-and-forget):
    uv run python modulate.py --id task-001 --no-wait hello.py

    # Check the status of a previous submission:
    uv run python modulate.py --get task-001

The job id (--id) is used as a stable key for Resonate's idempotency
guarantee: submitting the same id twice re-attaches to the existing run
rather than launching a second one.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

from resonate.context import Context
from resonate.resonate import Resonate
from resonate.retry import Never

RESONATE_URL = os.environ.get("RESONATE_URL", "http://localhost:8001")


# ---------------------------------------------------------------------------
# Workflow steps registered on the worker (gpu group).
# The stub here tells Resonate the function name and signature; the real
# implementation lives in worker.py and runs on a gpu-group worker process.
# ---------------------------------------------------------------------------

async def execute(ctx: Context, script_content: str, script_id: str) -> str: ...


# ---------------------------------------------------------------------------
# Durable workflows running on this process (entry group).
# ---------------------------------------------------------------------------

async def detached_rfi(ctx: Context, content: str, job_id: str, machine_type: str) -> None:
    """Fire-and-forget wrapper: dispatch execute to the target worker group."""
    await ctx.options(target=machine_type).rpc("execute", content, job_id)


async def prep_execute(
    ctx: Context,
    job_id: str,
    script: str,
    machine_type: str,
    wait: bool,
) -> str | None:
    """Read ``script`` and dispatch it to a worker in ``machine_type`` group.

    When ``wait`` is True the call blocks until the worker returns; when False
    the execution is detached and this function returns immediately.
    """
    try:
        with open(script) as f:
            content = f.read()

        print(f"Sending script to be executed on {machine_type}")
        if wait:
            result: str = await ctx.options(target=machine_type).rpc(
                "execute", content, job_id
            )
            return result
        else:
            await ctx.detached("detached_rfi", content, job_id, machine_type)
            return None

    except FileNotFoundError as e:
        print("Error: File not found.")
        raise e
    except Exception as e:
        print(f"An error occurred: {e}")
        raise e


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(description="Submit a Python script to a Modulate FaaS worker.")
    parser.add_argument(
        "-m", "--machine",
        dest="machine_type",
        default="gpu",
        help="Worker group to execute on (default: gpu).",
    )
    parser.add_argument(
        "-i", "--id",
        dest="id",
        help="Stable job id (defaults to a random uuid).",
    )
    parser.add_argument(
        "-w", "--no-wait",
        dest="wait",
        action="store_false",
        help="Return immediately without waiting for the result.",
    )
    parser.add_argument(
        "--get",
        dest="get_id",
        metavar="ID",
        help="Retrieve the result for a previously submitted job id.",
    )
    args, argv = parser.parse_known_args()

    resonate = Resonate(url=RESONATE_URL, group="entry")
    resonate.register(execute)
    resonate.register(detached_rfi, retry_policy=Never())
    resonate.register(prep_execute, retry_policy=Never())

    # Yield once so the HttpNetwork background start task runs before any
    # direct client call (e.g. promises.get) — avoids a startup-race error.
    await asyncio.sleep(0)

    try:
        if args.get_id is not None:
            promise_id = f"execution-{args.get_id}"
            try:
                record = await resonate.promises.get(promise_id)
                if record.state == "resolved":
                    print(f"Job results located at: {record.value.data}")
                else:
                    print(f"Job {args.get_id} is not ready yet (state: {record.state}).")
            except Exception:
                print(f"Job {args.get_id} not found or server unreachable.")
            return

        job_id = args.id or str(uuid.uuid4())
        print(f"You can retrieve this execution using {job_id}")

        if len(argv) < 1:
            print("Script name is required")
            raise SystemExit(1)

        print(f"Will execute {argv[0]} on {args.machine_type}...")
        handle = resonate.run(
            f"execution-{job_id}", prep_execute, job_id, argv[0], args.machine_type, args.wait
        )

        result = await handle.result()
        if result is not None:
            print(f"Results are located at {result}")

    finally:
        await resonate.stop()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
