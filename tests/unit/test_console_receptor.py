import time

from anima_ll.adapter.receptor.console_receptor import ConsoleReceptor


def lines(*values: str):
    it = iter(values)
    return lambda: next(it, "")


def drain_until(receptor: ConsoleReceptor, count: int) -> list:
    events: list = []
    deadline = time.monotonic() + 2.0
    while len(events) < count and time.monotonic() < deadline:
        events += receptor.drain()
        time.sleep(0.01)
    return events


def test_lines_are_drained_in_order_and_blank_lines_dropped() -> None:
    receptor = ConsoleReceptor("receptor.console", read_line=lines("ただいま\n", "\n", " 疲れた \n"))
    events = drain_until(receptor, 2)
    assert [e.payload for e in events] == ["ただいま", "疲れた"]
    assert all(e.receptor_id == "receptor.console" for e in events)


def test_eof_stops_reading_but_drain_keeps_working() -> None:
    receptor = ConsoleReceptor("receptor.console", read_line=lines())
    assert drain_until(receptor, 1) == []
    assert receptor.drain() == ()
