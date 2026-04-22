# Celery-like Job Queue — Technical Roadmap

## Overview

This project consists of building a background job execution system (job queue),
inspired by tools such as Celery or Sidekiq, implemented from scratch for learning purposes.

The focus is not on speed of delivery, but on:

-   deep understanding of asynchronous systems
-   concurrency and parallelism
-   reliability and fault tolerance
-   real-world system design

---

## Phase 0 — Analysis and Design

### Description

Clearly define the problem, system boundaries, and guarantees before writing any code.

### Goals

-   Define what a job is
-   Define the job lifecycle
-   Choose execution guarantees (at-least-once)
-   Design high-level architecture
-   Identify responsibilities (producer, queue, worker)

### Expected Outcomes

-   Simple architecture document
-   Explicit list of decisions and trade-offs

### Potential Pitfalls

-   Premature overengineering
-   Ambiguous job states
-   Mixing execution and orchestration responsibilities

---

## Phase 1 — Data Model and Core Queue

### Description

Implement the job queue using PostgreSQL as the core persistence layer.

### Goals

-   Create the `jobs` table
-   Define clear job states (pending, running, failed, done)
-   Guarantee atomic operations
-   Prevent duplicate processing

### Key Concepts

-   Transactions
-   `SELECT FOR UPDATE SKIP LOCKED`
-   Database-level locking
-   Indexing and performance

### Potential Pitfalls

-   Deadlocks
-   Jobs stuck in `running` state
-   Race conditions between workers

---

## Phase 2 — Worker and Job Execution

### Description

Build one or more workers responsible for consuming and executing jobs from the queue.

### Goals

-   Implement job polling loop
-   Execute payloads in isolation
-   Correctly update job state
-   Handle unexpected failures

### Key Concepts

-   Multiprocessing vs threading
-   Fault isolation
-   Process lifecycle management

### Potential Pitfalls

-   Duplicate execution
-   Worker crashes during job execution
-   Lack of idempotency

---

## Phase 3 — Retries and Backoff

### Description

Add recovery mechanisms for transient failures.

### Goals

-   Automatic retries
-   Exponential backoff
-   Maximum retry limits
-   Separation of transient vs permanent failures

### Key Concepts

-   Idempotency
-   Resilient system design
-   State management under failure

### Potential Pitfalls

-   Infinite retry loops
-   Database overload
-   Aggressive retry strategies

---

## Phase 4 — Observability

### Description

Provide visibility into the internal state of the system.

### Goals

-   Structured logging
-   Basic metrics (throughput, failures, execution time)
-   CLI for system inspection

### Key Concepts

-   Observability fundamentals
-   Operating systems in production
-   Debugging distributed systems

### Potential Pitfalls

-   Noisy logs
-   Lack of contextual information
-   Irrelevant metrics

---

## Phase 5 — Extensions and Enhancements

### Description

Optional advanced features to deepen understanding.

### Goals

-   Job prioritisation
-   Scheduled jobs (cron-like)
-   Dead letter queue
-   Plugin system for job types
-   Distributed workers across multiple machines

### Status

✅ **COMPLETED** - All Phase 5 features implemented.

---

## Phase 6 — Production Monitoring & Visibility

### Description

Enhanced observability tools for production deployments, enabling real-time monitoring and debugging.

### Goals

-   **Web Dashboard**: Browser-based UI for monitoring queues, jobs, and worker status in real-time
-   **Prometheus/OpenTelemetry Metrics**: Export metrics (queue depth, throughput, failure rates, execution times) for observability stacks
-   **Job Tags/Labels**: Arbitrary key-value metadata on jobs for filtering, searching, and dashboard grouping
-   **Enhanced CLI Tools**:
    - Queue statistics (pending/running/failed/dead counts)
    - Job history and search (filterable by tags/labels)
    - Replay dead jobs
    - Worker status listing
    - Queue performance metrics

### Key Concepts

-   Time-series databases (Prometheus)
-   Real-time web UI (Flask/FastAPI + WebSocket)
-   Metrics aggregation and exposition
-   Query optimization for dashboard queries

### Potential Pitfalls

-   Dashboard performance at scale
-   Metrics cardinality explosion
-   Authentication and authorization for dashboard

---

## Phase 7 — Worker Resilience & Job Control

### Description

Production-critical worker reliability features and fine-grained job control. These are foundational for any real deployment and should be prioritised early.

### Goals

-   **Worker Health Checks/Heartbeats**: Workers send periodic heartbeats, detecting stalled workers
-   **Lock Timeout Reclamation**: Automatically release locks from workers that stopped responding
-   **Graceful Worker Shutdown**: Drain in-flight jobs on SIGTERM/SIGINT instead of hard-killing, ensuring no work is lost during deployments
-   **Job Time Limits**: Maximum execution time per job, with automatic termination on timeout
-   **Job Cancellation**: Cancel pending jobs (remove from queue) or running jobs (cooperative cancellation via flag/signal)
-   **Concurrency Limits per Queue**: Cap how many jobs run simultaneously per queue (e.g., max 5 email jobs at once)

### Key Concepts

-   Heartbeat mechanism
-   Timeout detection and recovery
-   Signal handling (SIGTERM, SIGINT) and graceful drain
-   Process/thread termination
-   Cooperative cancellation patterns

### Potential Pitfalls

-   False positives in health checks
-   Zombie processes on timeout
-   Race conditions during shutdown (job claimed but worker exiting)
-   Cancellation of already-running jobs requires cooperation from job code

---

## Phase 8 — Advanced Job Features

### Description

Enhanced job processing capabilities building on top of the basic primitives from earlier phases.

### Goals

-   **Dynamic Priority & Priority Aging**: Enhance Phase 5's basic prioritisation with dynamic priority adjustment and aging to prevent starvation of low-priority jobs
-   **Rate Limiting**: Control job execution frequency per job type or queue (e.g., max 100 emails/hour)
-   **Custom Retry Strategies**: Pluggable backoff algorithms (linear, exponential with jitter, custom functions) extending Phase 3's basic exponential backoff
-   **Middleware/Hooks System**: Pre/post execution hooks for cross-cutting concerns (timing, tracing, audit logging, custom error handling)
-   **Job Result TTL & Cleanup**: Auto-purge old completed/dead jobs after a configurable retention period to prevent unbounded table growth

### Key Concepts

-   Priority aging algorithms
-   Token bucket or sliding window rate limiting
-   Strategy pattern for retry policies
-   Middleware pipeline pattern
-   Database maintenance and data lifecycle

### Potential Pitfalls

-   Starvation of low-priority jobs even with aging
-   Rate limit state management across distributed workers
-   Middleware ordering and error propagation
-   Cleanup jobs interfering with active queries

---

## Phase 9 — Scheduling & Workflows

### Description

Advanced job orchestration capabilities for complex task dependencies and recurring work.

### Goals

-   **Cron-like Recurring Jobs**: Define recurring schedules using cron syntax (e.g., `"0 * * * *"` for hourly), extending Phase 5's one-time scheduled jobs into persistent, repeating schedules
-   **Job Chains & Workflows**: Jobs that trigger other jobs on success/failure (chaining), with configurable failure propagation strategies
-   **Job Groups & Chords**: Run N jobs in parallel (group) and execute a callback when all complete (chord), inspired by Celery's primitives
-   **Job Dependencies (DAGs)**: Jobs that wait for other jobs to complete before starting, enabling complex directed acyclic graph workflows
-   **Bulk Enqueue**: Efficiently enqueue multiple jobs in a single database transaction

### Key Concepts

-   Cron expression parsing and schedule persistence
-   Workflow orchestration patterns
-   Fan-out / fan-in (scatter-gather) patterns
-   Directed Acyclic Graphs (DAGs) for dependencies
-   Batch database operations

### Potential Pitfalls

-   Circular dependency detection
-   Chain/chord failure propagation and partial completion handling
-   Cron drift and missed schedule recovery
-   Group completion tracking with concurrent workers

---

## Phase 10 — Notifications & External Integrations

### Description

Outbound communication and integration with external systems for event-driven architectures.

### Goals

-   **Webhooks**: External HTTP notifications on job completion/failure with retry and delivery guarantees
-   **Circuit Breakers**: Stop processing job types that are consistently failing, with automatic recovery after cooldown
-   **Event Bus Integration**: Publish job lifecycle events to external message queues (RabbitMQ, Kafka)

### Key Concepts

-   HTTP webhook delivery with retry
-   Circuit breaker pattern (closed/open/half-open states)
-   Event-driven architecture
-   Message queue integration and delivery guarantees

### Potential Pitfalls

-   Webhook delivery guarantees and idempotency
-   Circuit breaker threshold tuning
-   Message ordering guarantees across brokers

---

## Phase 11 — API & Real-time Features

### Description

Programmatic interfaces for external system integration and real-time visibility.

### Goals

-   **Result API**: REST endpoint to retrieve job results and status programmatically
-   **Admin REST API**: Full CRUD operations on jobs, queues, and workers
-   **WebSocket Support**: Real-time updates on job status changes, powering live dashboard updates
-   **Multi-tenancy / Namespaces**: Isolate jobs by tenant or namespace, enabling shared service deployments with per-tenant quotas and visibility

### Key Concepts

-   REST API design and authentication
-   WebSocket connections and scaling
-   Tenant isolation patterns (shared DB with namespace column vs schema-per-tenant)
-   API rate limiting and authorization

### Potential Pitfalls

-   API authentication and security
-   WebSocket connection scaling
-   Tenant data leakage
-   Noisy neighbour problem in multi-tenant setups

---

## Conclusion

This project is not about frameworks.
It is about engineering, trade-offs, and building systems that fail — and recover.

The journey from Phase 0 to Phase 11 represents a complete evolution from a learning project to a production-ready job queue system, covering everything from basic queuing to advanced orchestration, resilience, and integration capabilities.
