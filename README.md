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
│   Client    │ Submit function execution
│  (HTTP/CLI) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  modulate   │ Router (entry worker group)
│  (Router)   │ - Accepts function submissions
└──────┬──────┘ - Routes to appropriate workers
       │
       ├──────────────┐
       ▼              ▼
┌─────────────┐  ┌─────────────┐
│   worker    │  │   worker    │
│   (GPU)     │  │   (CPU)     │
└─────────────┘  └─────────────┘
  Execute code    Execute code
```

**Components:**

1. **Router (modulate.py)** - Entry point that accepts function submissions and routes them to workers
2. **Workers (worker.py)** - Execute user functions in specialized groups (GPU, CPU, etc.)
3. **Resonate Server** - Coordinates message passing and provides durability

## What This Demonstrates

- **Task Routing** - Directing work to specific worker groups (GPU vs CPU)
- **RPC (Remote Function Call)** - Blocking calls that wait for results
- **RFI (Remote Function Invocation)** - Fire-and-forget calls
- **Detached Execution** - Background tasks that don't block the caller
- **Worker Groups** - Organizing workers by capability (GPU, CPU)

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
resonate dev
```

### 2. Start the Router (Entry Worker)

```bash
uv run python modulate.py --mode router
```

This starts the entry worker group that accepts function submissions.

### 3. Start Worker(s)

In separate terminals, start workers for different groups:

**GPU Worker:**
```bash
uv run python worker.py --group gpu
```

**CPU Worker (optional):**
```bash
uv run python worker.py --group cpu
```

The workers poll Resonate for tasks routed to their group.

## Usage

### Submit a Function for Execution

**Fire-and-Forget (RFI):**
```bash
uv run python modulate.py --script hello.py --id task-001 --machine-type gpu
```

Returns immediately. The function executes in the background.

**Wait for Result (RPC):**
```bash
uv run python modulate.py --script hello.py --id task-002 --machine-type gpu --wait
```

Blocks until the function completes and returns the result.

### Check Execution Status

```bash
uv run python modulate.py --get task-001
```

Returns the result if execution completed, or `None` if still running.

## Example Function

Create a Python script (`hello.py`):

```python
# hello.py
print("Hello from Modulate FaaS!")

# Simulate GPU work
import time
time.sleep(2)

result = {"message": "Computation complete", "status": "success"}
print(f"Result: {result}")
```

Submit it:
```bash
uv run python modulate.py --script hello.py --id gpu-job-1 --machine-type gpu
```

## How It Works

### 1. Function Submission (Router)

[modulate.py:31](modulate.py#L31-L46) - The router reads your script and submits it to the appropriate worker group:

```python
@resonate.register(retry_policy=never())
def prep_execute(ctx: Context, id, script, machine_type, wait):
    with open(script, "r") as file:
        content = file.read()

    if wait:
        # RPC: Wait for result
        result = yield ctx.rfc(execute, content, id).options(
            id=id, send_to=poll("gpu")
        )
        return result
    else:
        # RFI: Fire and forget
        yield ctx.detached(detached_id, detached_rfi, content, id, "gpu")
        return None
```

### 2. Function Execution (Worker)

[worker.py](worker.py) - Workers in the "gpu" group pick up tasks and execute them:

```python
@resonate.register()
def execute(ctx: Context, script_content, id):
    exec(script_content)
    return {"id": id, "status": "completed"}
```

### 3. Result Retrieval

[modulate.py:13](modulate.py#L13-L18) - Check if execution completed:

```python
def get_by_id(id):
    record = resonate.promises.get(id=id)
    if record.is_completed:
        return record.value.data
    return None
```

## Key Concepts

### Worker Groups

Workers register with a specific group (`gpu`, `cpu`, etc.). The router directs tasks to groups using `send_to=poll("gpu")`.

This enables:
- GPU-intensive workloads → GPU workers
- CPU-bound tasks → CPU workers
- Custom hardware → Specialized worker groups

### RPC vs RFI

- **RPC (Remote Function Call)** - `ctx.rfc()` - Waits for result, blocks caller
- **RFI (Remote Function Invocation)** - `ctx.rfi()` - Fire-and-forget, returns immediately

### Detached Execution

`ctx.detached()` starts a background task that doesn't block the caller. Useful for:
- Long-running computations
- Background processing
- Fire-and-forget tasks

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

- [Resonate Python SDK Docs](https://docs.resonatehq.io/sdk/python)
- [Task Routing Patterns](https://docs.resonatehq.io/patterns/routing)
- [RPC vs RFI](https://docs.resonatehq.io/concepts/rpc-rfi)

## Related Examples

- [example-load-balancing-py](../example-load-balancing-py) - Worker pool patterns
- [example-async-rpc-py](../example-async-rpc-py) - Cross-process communication
- [example-kafka-worker-py](../example-kafka-worker-py) - Message queue workers
