from .hitl_task_poller import start_hitl_polling_service
from .pa_status_poller import start_PA_polling_service
from .agent.workflow import create_workflow
from .intake_scenarios import get_intake


from .agent.state import PAIntake, PAAgentState
from uuid import uuid4
from datetime import datetime, timedelta, UTC
import asyncio


async def main(intake_id: str):
    await start_hitl_polling_service()
    await start_PA_polling_service()

    intake = PAIntake(**(get_intake(intake_id)))

    print("=" * 50)
    print(f"Running PA workflow for {intake.pa_request_id}")
    print("=" * 50)
    
    workflow = create_workflow()
    config = {"configurable": {"thread_id": intake.pa_request_id}}
    await workflow.ainvoke(intake, config=config)
    
    # Keep running to let pollers work
    print("\nPollers running. Press Ctrl+C to exit.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        intake_id = sys.argv[1]
        asyncio.run(main(intake_id))
    else:
        print("No intake id provided.")
