from masim.models.state import State

def code_analyzer_router(state: State):
    return "FIX" if state["need_fix"] and state["retry"] <= state["max_retry"] else "END"
