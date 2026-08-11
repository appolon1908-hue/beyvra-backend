"""FIX protocol state and fixture parsing only. No socket transport exists here."""
from dataclasses import dataclass

SESSION_TRANSITIONS={"DISCONNECTED":{"CONNECTING"},"CONNECTING":{"LOGGED_ON","FAILED"},"LOGGED_ON":{"RECOVERING","LOGGING_OUT","FAILED"},"RECOVERING":{"LOGGED_ON","FAILED"},"LOGGING_OUT":{"DISCONNECTED"},"FAILED":{"DISCONNECTED"}}

@dataclass
class FixSessionState:
    state:str="DISCONNECTED"
    incoming_seq:int=1
    outgoing_seq:int=1

class FixExecutionGateway:
    supported_messages={"A","5","0","1","2","4","D","F","G","8","9","j"}
    def __init__(self): self.session=FixSessionState(); self.execution_ids=set()
    def transition(self,state):
        if state not in SESSION_TRANSITIONS.get(self.session.state,set()): raise ValueError("INVALID_FIX_SESSION_TRANSITION")
        self.session.state=state; return state
    def send(self,message_type):
        if message_type not in self.supported_messages: raise ValueError("FIX_MESSAGE_UNSUPPORTED")
        if message_type in {"D","F","G"}: raise RuntimeError("FIX_LIVE_SESSION_DISABLED")
        self.session.outgoing_seq+=1
    def receive(self,message):
        seq=int(message["34"]); expected=self.session.incoming_seq
        if seq>expected: self.session.state="RECOVERING"; return {"action":"RESEND_REQUEST","begin_seq":expected,"end_seq":seq-1}
        if seq<expected and message.get("43")!="Y": raise ValueError("FIX_SEQUENCE_REGRESSION")
        self.session.incoming_seq=max(expected,seq+1)
        if message.get("35")=="8" and message.get("17"):
            duplicate=message["17"] in self.execution_ids; self.execution_ids.add(message["17"]); return {"execution_id":message["17"],"duplicate":duplicate,"business_effects":0 if duplicate else 1}
        return {"accepted":True}
