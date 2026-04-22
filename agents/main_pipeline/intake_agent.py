from intake_agent.agents import create_envelope
from intake_agent.agents import run

def intake_agent(raw_text: str) -> dict:
    envelope = create_envelope(raw_text)
    envelope = run(envelope)

    return envelope


# email = '''Subject: Urgent Laptop Replacement Needed

# Hi IT Team,

# My laptop screen cracked this morning after it slipped from my desk. 
# The display is flickering badly and I can barely read anything on it.

# I need a replacement as soon as possible since I use this laptop for daily reporting and meetings.

# Thanks,
# Ahmed Hassan
# Finance Department'''

# print(intake_agent(email))