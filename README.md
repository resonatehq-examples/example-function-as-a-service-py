<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="./assets/banner-light.png">
    <img alt="Function as a Service — Resonate example" src="./assets/banner-dark.png">
  </picture>
</p>

# Modulate: On-Premise FaaS Platform with Resonate

**A demo Function-as-a-Service platform demonstrating how to build infrastructure with Resonate.**

Modulate shows how to use Resonate to build a distributed FaaS platform that routes workloads to specialized workers (like GPU nodes) with automatic crash recovery and durable execution.

## Why Build an On-Premise FaaS Platform?

Function-as-a-Service (FaaS) is a cloud computing model that lets developers deploy individual pieces of code—called functions—without managing servers or infrastructure. These functions are triggered by specific events, like an HTTP request, a file upload, or a database update. The cloud provider (e.g., AWS Lambda, Azure Functions) automatically handles scaling, resource allocation, and runtime environments. You pay only for the compute time your functions consume, in millisecond increments.

The "serverless" nature of FaaS means developers focus purely on writing code to solve problems, while the provider abstracts away servers, virtual machines, and containers. However, "serverless" doesn't mean there are no servers—it means you don't see or manage them.

### Why On-Premise?

Building an on-premise FaaS platform might seem counterintuitive, but it offers unique benefits:

- **GPU and AI Workloads** - Direct access to specialized hardware
- **Data Privacy** - Sensitive data never leaves your infrastructure
- **Cost Predictability** - No per-invocation charges, fixed infrastructure costs
- **Compliance** - Meet regulatory requirements for data locality
- **Custom Hardware** - Leverage proprietary accelerators or specialized chips

## Why Resonate?

Resonate is designed to make distributed systems as straightforward as writing `async/await` code. This makes it ideal for building an on-prem FaaS platform:

- **Distributed Async/Await** - Write functions as simple `async/await` code while Resonate guarantees crash-resistant execution
- **Routing** - Tasks are directed to the right workers seamlessly based on user input or defined criteria
- **Durability** - Automatic retries and built-in replayability ensure functions survive hardware failures and network issues

These features make Resonate an excellent choice for building a FaaS platform, especially for on-premise use cases where control, security, and cost predictability are critical.

## Architecture

```
┌─────────────┐
│  modulate   │ Client (CLI)
│   (client)  │ - Reads the script
└──────┬──────┘ - Submits it to a machine-type group
       │
       ├──────────────┐
       ▼              ▼
┌─────────────┐  ┌─────────────┐
│   worker    │  │   worker    │
│   (gpu)     │  │   (cpu)     │
└─────────────┘  └─────────────┘
  Execute code    Execute code
```

**Components:**

1. **Client (modulate.py)** - Reads your script and submits it to a machine-type worker group
2. **Workers (worker.py)** - Execute submitted scripts, one group per machine type (gpu, cpu, etc.)
3. **Resonate Server** - Coordinates message passing and provides durability

The client is thin on purpose. Once the job is submitted it lives on the Resonate server, so the client can exit, crash, or be restarted without losing the execution — that is what `--get` reconnects to.

## What This Demonstrates

- **Task Routing** - Directing work to specific worker groups (gpu vs cpu)
- **Ephemeral to durable** - A CLI process hands work to a durable execution and walks away
- **Blocking and non-blocking submission** - Await the result now, or look it up later by job id
- **Worker Groups** - Organizing workers by capability (gpu, cpu)

## Prerequisites

- Python 3.12+
- uv (Python package manager)
- Resonate server running

## Installation

```bash
# Install dependencies
uv sync
```

## Running the Platform

### 1. Start Resonate Server

```bash
resonate serve
```

### 2. Start Worker(s)

In separate terminals, start a worker per machine type. `MACHINE_TYPE` is the group the worker joins, and is what `--machine` routes to. It defaults to `gpu`.

**GPU Worker:**
```bash
uv run python worker.py
```

**CPU Worker (optional):**
```bash
MACHINE_TYPE=cpu uv run python worker.py
```

The workers poll Resonate for tasks routed to their group.

## Usage

The script to run is a positional argument.

### Submit and wait for the result

```bash
uv run python modulate.py -i task-001 hello.py
```

Blocks until the script finishes, then prints where its output was written.

### Submit without waiting

```bash
uv run python modulate.py -i task-002 -w hello.py
```

Returns as soon as the job is durably recorded. It keeps running on the worker.

### Route to a different machine type

```bash
uv run python modulate.py -i task-003 -m cpu hello.py
```

### Check execution status

```bash
uv run python modulate.py --get task-002
```

Prints where the results are if the job has resolved, or that it is not ready yet.

If you do not pass `-i`, a random uuid is used and printed — that is the id `--get` needs.

## Example Function

`hello.py` in this repo is a stand-in for a long GPU job: it prints, sleeps for 30 seconds, then prints a batch of results. Any Python script works. The worker runs it in an isolated interpreter (`python -I -S`) inside a temporary directory, and writes its streams to `<id>.sout` and `<id>.eout` in the worker's working directory.

## How It Works

### 1. Function Submission (Client)

[modulate.py](modulate.py) - The client reads your script and submits it to the machine-type group:

```python
handle = resonate.options(target=args.machine_type).rpc(
    job_id, "execute", content, job_id
)

if args.wait:
    result = await handle.result()
else:
    # Wait for the promise to exist on the server, then leave.
    await handle.id()
```

`job_id` is the id of the top-level promise. The caller picks it, which is what makes `--get` possible later.

### 2. Function Execution (Worker)

[worker.py](worker.py) - Workers in the targeted group pick up tasks and execute them:

```python
async def execute(ctx: Context, script_content: str, script_id: str) -> str:
    # subprocess.run blocks, so keep it off the worker's event loop.
    return await asyncio.to_thread(run_script, script_content, script_id)
```

### 3. Result Retrieval

[modulate.py](modulate.py) - Check if execution completed:

```python
async def get_by_id(resonate: Resonate, job_id: str) -> str | None:
    record = await resonate.promises.get(job_id)
    if record.state == "resolved":
        return record.value.data if record.value else None
    return None
```

## Key Concepts

### Worker Groups

Workers join a group (`gpu`, `cpu`, ...). The client directs a job to a group by naming it as the target: `resonate.options(target="gpu")`. Any available worker in that group picks it up.

This enables:
- GPU-intensive workloads → GPU workers
- CPU-bound tasks → CPU workers
- Custom hardware → Specialized worker groups

### Blocking and non-blocking submission

`resonate.rpc()` invokes a function in a remote process and returns a handle immediately. What you do with the handle decides the shape of the call:

- `await handle.result()` waits for the execution to finish — a blocking call.
- `await handle.id()` waits only for the promise to be created, then lets the client exit while the work continues.

Awaiting *something* before exiting matters: the SDK creates the promise on a background task, so a client that exits the instant after calling `rpc()` can tear its network down before the job is registered.

### Crash Recovery

If a worker crashes mid-execution, Resonate automatically:
1. Detects the failure
2. Retries the function on another worker in the same group
3. Ensures exactly-once execution semantics

## Production Considerations

For production use:

1. **Resource Limits** - Add CPU/memory limits to prevent resource exhaustion
2. **Isolation** - Use containers or VMs to isolate function execution
3. **Security** - Validate and sanitize uploaded code
4. **Monitoring** - Track execution times, failure rates, resource usage
5. **Scaling** - Add more workers dynamically based on queue depth
6. **Authentication** - Add auth for function submission
7. **Rate Limiting** - Prevent abuse with request limits

## Use Cases

This pattern applies to:

- **ML Model Inference** - Route requests to GPU workers for inference
- **Video Processing** - Leverage GPU acceleration for transcoding
- **Scientific Computing** - Distribute workloads across HPC clusters
- **Data Processing** - Route jobs to workers with specific capabilities
- **Edge Computing** - Deploy workers close to data sources

## Learn More

- [Resonate Python SDK Docs](https://docs.resonatehq.io/develop/python)
- [Running the Resonate Server](https://docs.resonatehq.io/deploy/run-server)
- [More examples](https://docs.resonatehq.io/get-started/examples)

## Related Examples

- [example-async-rpc-py](https://github.com/resonatehq-examples/example-async-rpc-py) - Cross-process communication
- [example-fan-out-fan-in-py](https://github.com/resonatehq-examples/example-fan-out-fan-in-py) - Parallel work with durable fan-in
