from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile

from resonate.context import Context
from resonate.resonate import Resonate

RESONATE_URL = os.environ.get("RESONATE_URL", "http://localhost:8001")


async def execute(ctx: Context, script_content: str, script_id: str) -> str:
    """Execute Python script content in a sandboxed environment.

    Writes stdout to ``{script_id}.sout`` and stderr to ``{script_id}.eout``,
    then returns the stdout filename.
    """
    temp_dir = tempfile.mkdtemp()
    output_filename = f"{script_id}.sout"
    errput_filename = f"{script_id}.eout"
    print("executing script...")

    err: str | None = None
    output: str | None = None
    try:
        script_path = os.path.join(temp_dir, f"sandboxed_script-{script_id}.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        result = subprocess.run(
            ["python", "-I", "-S", script_path],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=True,
        )

        output = result.stdout
        err = result.stderr

    except subprocess.TimeoutExpired:
        err = "Error: Execution timed out after 120 seconds"
    except subprocess.CalledProcessError as e:
        err = (
            f"Error: Process returned {e.returncode}\n"
            f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        )
    except Exception as e:
        err = f"Unexpected error: {str(e)}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("Done executing")
    print("Writing out results")

    with open(output_filename, "w") as f:
        if output:
            f.write(output)

    with open(errput_filename, "w") as f:
        if err:
            f.write(err)

    print("Done!")
    return output_filename


async def main() -> None:
    resonate = Resonate(url=RESONATE_URL, group="gpu")
    resonate.register(execute)

    print("[worker] starting — registered: execute")
    print("[worker] waiting for work from the Resonate server...")

    try:
        await asyncio.Event().wait()
    finally:
        await resonate.stop()


if __name__ == "__main__":
    asyncio.run(main())
