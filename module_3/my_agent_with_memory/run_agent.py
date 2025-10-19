# run_agent.py (Final Code)

import asyncio
from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import load_memory
from google.genai.types import Content, Part
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# 1. Define Constants
APP_NAME = "memory_lab_app"
USER_ID = "test_user_123"
MODEL = "gemini-2.5-flash"

# 2. Define Agents
info_capture_agent = LlmAgent(
    model=MODEL,
    name="InfoCaptureAgent",
    instruction="You are an assistant. Acknowledge the user's statement in a friendly tone.",
)

memory_recall_agent = LlmAgent(
    model=MODEL,
    name="MemoryRecallAgent",
    instruction="Answer the user's question. Use the 'load_memory' tool "
                "if the answer might be in past conversations.",
    tools=[load_memory]
)

# 3. Define the Main Scenario Logic
async def run_memory_scenario():
    """Runs a two-turn scenario to demonstrate memory."""
    print("🚀 Scenario starting with InMemoryMemoryService!")

    # Instantiate the services that will be shared.
    session_service = InMemorySessionService()
    memory_service = InMemoryMemoryService()

    # TURN 1: CAPTURE AND STORE INFORMATION
    print("\n--- Turn 1: Capturing Information ---")
    runner1 = Runner(
        agent=info_capture_agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service
    )
    session1_id = "session_for_storing"
    await runner1.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session1_id
    )
    user_input1 = Content(parts=[Part(text="My favorite color is blue.")], role="user")

    print(f"👤 User Input: {user_input1.parts[0].text}")

    async for event in runner1.run_async(
        user_id=USER_ID, session_id=session1_id, new_message=user_input1
    ):
        if event.is_final_response() and event.content and event.content.parts:
            print(f"🤖 Agent 1 Response: {event.content.parts[0].text}")

    print("\n--- Adding Session 1 to Memory ---")
    completed_session1 = await runner1.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session1_id
    )
    await memory_service.add_session_to_memory(completed_session1)
    print("✅ Session added to memory.")

    # TURN 2: RECALL INFORMATION IN A NEW SESSION
    print("\n--- Turn 2: Recalling Information ---")
    runner2 = Runner(
        agent=memory_recall_agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service
    )
    session2_id = "session_for_recalling"
    await runner2.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session2_id
    )
    user_input2 = Content(parts=[Part(text="What is my favorite color?")], role="user")

    print(f"👤 User Input: {user_input2.parts[0].text}")

    async for event in runner2.run_async(
        user_id=USER_ID, session_id=session2_id, new_message=user_input2
    ):
        if event.is_final_response() and event.content and event.content.parts:
            print(f"🤖 Agent 2 Response: {event.content.parts[0].text}")

# --- 4. Run the Script ---
if __name__ == "__main__":
    # NOTE: You may need to set your GOOGLE_API_KEY environment variable.
    asyncio.run(run_memory_scenario())




# Need to set GOOGLE_API_KEY