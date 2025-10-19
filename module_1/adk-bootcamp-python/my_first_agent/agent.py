# from google.adk.agents.llm_agent import Agent

# root_agent = Agent(
#     model='gemini-2.5-flash',
#     name='root_agent',
#     description='A helpful assistant for user questions.',
#     instruction='Answer user questions to the best of your knowledge',
# )


from google.adk.agents import LlmAgent

# The ADK runtime looks for an object named `root_agent`
# in main.py to start the application.
root_agent = LlmAgent(
    name="assistant_agent",
    model="gemini-2.5-flash",
    description="A helpful and creative assistant for a wide range of tasks.",
    instruction="""
You are a friendly and knowledgeable assistant named Alex.
Your goal is to help users with their questions clearly and concisely.
When asked for creative tasks, like writing a poem or a joke, be imaginative!
"""
)