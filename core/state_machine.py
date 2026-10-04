"""Explicit assistant lifecycle; voice states are reserved until capture is implemented."""

from core.models import State

TRANSITIONS = {
    State.IDLE: {State.LISTENING, State.THINKING},
    State.LISTENING: {State.THINKING, State.IDLE, State.ERROR},
    State.THINKING: {State.EXECUTING, State.IDLE, State.ERROR},
    State.EXECUTING: {State.SPEAKING, State.IDLE, State.ERROR},
    State.SPEAKING: {State.IDLE, State.ERROR},
    State.ERROR: {State.IDLE, State.THINKING, State.LISTENING},
}


class StateMachine:
    def __init__(self) -> None:
        self.state = State.IDLE

    def transition(self, state: State) -> None:
        if state not in TRANSITIONS[self.state]:
            raise ValueError(f"Invalid assistant transition: {self.state} → {state}")
        self.state = state
