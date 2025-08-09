# stub: Linear API client
class LinearClient:
    def __init__(self, token: str|None=None):
        self.token = token
    def create_issue(self, *a, **k):
        raise NotImplementedError("LINEAR_ENABLED=false")
    def comment(self, *a, **k):
        raise NotImplementedError("LINEAR_ENABLED=false")
    def transition(self, *a, **k):
        raise NotImplementedError("LINEAR_ENABLED=false")
