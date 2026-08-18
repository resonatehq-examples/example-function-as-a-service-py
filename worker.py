"""A Modulate worker.

Each worker joins a machine-type group (``gpu``, ``cpu``, ...) and executes the
scripts routed to that group. Set ``MACHINE_TYPE`` to pick the group.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

from resonate.resonate import Resonate

if TYPE_CHECKING:
    from resonate.context import Context

SCRIPT_TIMEOUT_SECONDS = 120


def run_script(script_content: str, script_id: str) -> str:
    """Run a script in a sandboxed temp directory and write out its streams."""
    temp_dir = tempfile.mkdtemp()
    output_filename = f"{script_id}.sout"
    errput_filename = f"{script_id}.eout"
    print("executing script...", flush=True)

    err = None
    output = None
    try:
        # Create script file in temporary directory
        script_path = os.path.join(temp_dir, f"sandboxed_script-{script_id}.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        # Execute script with security measures
        result = subprocess.run(
            ["python", "-I", "-S", script_path],  # Isolated mode with minimal imports
            cwd=temp_dir,  # Contain files in temp directory
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,  # Prevent infinite loops
            check=True,
        )

        output = result.stdout
        err = result.stderr

    except subprocess.TimeoutExpired:
        err = f"Error: Execution timed out after {SCRIPT_TIMEOUT_SECONDS} seconds"
    except subprocess.CalledProcessError as e:
        err = f"Error: Process returned {e.returncode}\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
    except Exception as e:
        err = f"Unexpected error: {str(e)}"
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("Done executing", flush=True)
    print("Writing out results", flush=True)

    # Write output to result file
    with open(output_filename, "w") as f:
        if output:
            f.write(output)

    with open(errput_filename, "w") as f:
        if err:
            f.write(err)

    print("Done!", flush=True)
    return output_filename


async def execute(ctx: Context, script_content: str, script_id: str) -> str:
    """Execute the given Python script content and save its output to [id].sout.

    Args:
        script_content (str): Python code to execute
        script_id (str): Unique identifier for the output files

    Returns:
        str: The name of the file the script's stdout was written to
    """
    # subprocess.run blocks. Running it on a thread keeps the worker's event
    # loop free to heartbeat its lease and serve other executions meanwhile.
    return await asyncio.to_thread(run_script, script_content, script_id)


async def main() -> None:
    machine_type = os.environ.get("MACHINE_TYPE", "gpu")

    resonate = Resonate(
        url=os.environ.get("RESONATE_URL", "http://localhost:8001"),
        group=machine_type,
    )
    resonate.register(execute)

    print(f"Running worker for machine type: {machine_type}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
