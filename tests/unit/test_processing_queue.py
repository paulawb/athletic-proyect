import asyncio

from app.infrastructure.tasks.processing_queue import run_one_at_a_time, waiting_analysis_ids


async def test_processes_one_analysis_at_a_time_and_reports_the_waiting_ones() -> None:
    events: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first_job() -> None:
        events.append("inicio 1")
        first_started.set()
        await release_first.wait()
        events.append("fin 1")

    async def second_job() -> None:
        events.append("inicio 2")

    first = asyncio.create_task(run_one_at_a_time(1, first_job))
    await first_started.wait()
    second = asyncio.create_task(run_one_at_a_time(2, second_job))
    await asyncio.sleep(0)

    assert waiting_analysis_ids() == frozenset({2})

    release_first.set()
    await asyncio.gather(first, second)

    assert events == ["inicio 1", "fin 1", "inicio 2"]
    assert waiting_analysis_ids() == frozenset()


async def test_a_failing_job_does_not_block_the_next_one() -> None:
    async def failing_job() -> None:
        raise RuntimeError("fallo")

    ran: list[int] = []

    async def next_job() -> None:
        ran.append(2)

    await run_one_at_a_time(1, failing_job)
    await run_one_at_a_time(2, next_job)

    assert ran == [2]
