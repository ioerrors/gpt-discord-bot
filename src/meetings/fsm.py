# stub: meeting finite state machine
from enum import Enum, auto

class State(Enum):
    IDLE = auto()
    CANDIDATE = auto()
    ACTIVE = auto()
    FINALIZE = auto()

class MeetingFSM:
    def __init__(self):
        self.state = State.IDLE
