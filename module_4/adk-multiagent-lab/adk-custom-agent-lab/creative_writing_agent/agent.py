import logging
from typing import AsyncGenerator
from typing_extensions import override

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.events import Event
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
GEMINI_2_FLASH = "gemini-2.0-flash"

# --- Individual Specialist Agents ---

story_generator = LlmAgent(
    name="StoryGenerator",
    model=GEMINI_2_FLASH,
    description="Creates original short stories based on given topics.",
    instruction="""You are a creative story writer. Write a compelling short story (around 100-150 words)
    based on the following topic: {topic}

    Make the story engaging with:
    - Clear characters and setting
    - An interesting conflict or challenge
    - A satisfying resolution

    Focus on creativity and emotional impact.""",
    output_key="current_story"  # Saves output to session state
)

critic = LlmAgent(
    name="StoryCritic",
    model=GEMINI_2_FLASH,
    description="Provides constructive criticism to improve stories.",
    instruction="""You are an expert story critic. Review this story: {current_story}

    Provide 1-2 sentences of constructive criticism focusing on:
    - Character development
    - Plot structure
    - Emotional impact
    - Clarity and flow

    Be specific and actionable in your feedback.""",
    output_key="criticism"
)

reviser = LlmAgent(
    name="StoryReviser",
    model=GEMINI_2_FLASH,
    description="Revises stories based on critical feedback.",
    instruction="""You are a story editor. Revise this story: {current_story}

    Apply this criticism: {criticism}

    Improve the story while maintaining its core essence. Output only the revised story.""",
    output_key="current_story"  # Overwrites the original story
)

grammar_check = LlmAgent(
    name="GrammarChecker",
    model=GEMINI_2_FLASH,
    description="Analyzes grammar and writing quality.",
    instruction="""You are a grammar and style checker. Analyze this story: {current_story}

    Check for:
    - Grammar errors
    - Sentence structure
    - Word choice
    - Clarity issues

    If the grammar is good, respond with 'Grammar is excellent!'
    Otherwise, provide a brief list of specific improvements needed.""",
    output_key="grammar_suggestions"
)

tone_check = LlmAgent(
    name="ToneAnalyzer",
    model=GEMINI_2_FLASH,
    description="Analyzes the emotional tone of stories.",
    instruction="""You are a tone analyzer. Analyze the overall emotional tone of this story: {current_story}

    Consider the story's mood, atmosphere, and emotional impact.

    Respond with exactly one word:
    - 'positive' if the tone is uplifting, hopeful, or joyful
    - 'negative' if the tone is dark, sad, or depressing
    - 'neutral' if the tone is balanced or neither strongly positive nor negative""",
    output_key="tone_check_result"  # This determines conditional flow
)

# --- Custom Orchestrator Agent ---

class StoryFlowAgent(BaseAgent):
    """
    Custom agent for a story generation and refinement workflow.

    This agent demonstrates advanced orchestration by combining:
    - Initial story generation
    - Iterative critic-reviser loop (LoopAgent pattern)
    - Parallel quality checks (SequentialAgent pattern)
    - Conditional logic based on tone analysis
    """

    # Pydantic field declarations for type safety
    story_generator: LlmAgent
    critic: LlmAgent
    reviser: LlmAgent
    grammar_check: LlmAgent
    tone_check: LlmAgent

    # Internal workflow agents
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent

    # Allow arbitrary types for Pydantic
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        story_generator: LlmAgent,
        critic: LlmAgent,
        reviser: LlmAgent,
        grammar_check: LlmAgent,
        tone_check: LlmAgent,
    ):
        """
        Initialize the StoryFlowAgent with all required specialist agents.

        Args:
            name: The name of the custom agent
            story_generator: Agent to create initial stories
            critic: Agent to provide story criticism
            reviser: Agent to revise stories based on criticism
            grammar_check: Agent to check grammar and style
            tone_check: Agent to analyze story tone
        """
        # Create internal workflow agents BEFORE calling super().__init__
        loop_agent = LoopAgent(
            name="CriticReviserLoop",
            sub_agents=[critic, reviser],
            max_iterations=2,  # Limit iterations to prevent infinite loops
            description="Iteratively improves story through critic-reviser cycles"
        )

        sequential_agent = SequentialAgent(
            name="QualityChecks",
            sub_agents=[grammar_check, tone_check],
            description="Performs grammar and tone analysis in sequence"
        )

        # Define sub_agents for the framework
        sub_agents_list = [
            story_generator,
            loop_agent,
            sequential_agent,
        ]

        # Call parent constructor with all required parameters
        super().__init__(
            name=name,
            story_generator=story_generator,
            critic=critic,
            reviser=reviser,
            grammar_check=grammar_check,
            tone_check=tone_check,
            loop_agent=loop_agent,
            sequential_agent=sequential_agent,
            sub_agents=sub_agents_list,
            description="Custom orchestrator for creative writing workflow with conditional logic"
        )

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Implements the custom orchestration logic for the story workflow.

        Workflow:
        1. Generate initial story
        2. Run critic-reviser loop for iterative improvement
        3. Perform quality checks (grammar and tone)
        4. Conditionally regenerate if tone is negative
        """
        logger.info(f"[{self.name}] Starting creative writing workflow")

        # Extract topic from user message or session state
        topic = ctx.session.state.get("topic")

        # If no topic in state, extract from the user's current message
        if not topic and ctx.user_content and ctx.user_content.parts:
            topic = ctx.user_content.parts[0].text.strip()
            # Store the topic in session state for consistency
            ctx.session.state["topic"] = topic
            logger.info(f"[{self.name}] Extracted topic from user message: {topic}")

        if not topic:
            logger.error(f"[{self.name}] No topic provided in user message or session state")
            return

        logger.info(f"[{self.name}] Working on topic: {topic}")

        # 1. Initial Story Generation
        logger.info(f"[{self.name}] Step 1: Generating initial story")
        async for event in self.story_generator.run_async(ctx):
            logger.info(f"[{self.name}] StoryGenerator event: {event.model_dump_json(exclude_none=True)}")
            yield event

        # Verify story was generated
        if "current_story" not in ctx.session.state or not ctx.session.state["current_story"]:
            logger.error(f"[{self.name}] Failed to generate initial story. Aborting workflow.")
            return

        initial_story = ctx.session.state["current_story"]
        logger.info(f"[{self.name}] Generated story: {initial_story[:100]}...")

        # 2. Critic-Reviser Loop for Iterative Improvement
        logger.info(f"[{self.name}] Step 2: Running critic-reviser improvement loop")
        async for event in self.loop_agent.run_async(ctx):
            logger.info(f"[{self.name}] CriticReviserLoop event: {event.model_dump_json(exclude_none=True)}")
            yield event

        improved_story = ctx.session.state.get("current_story", initial_story)
        logger.info(f"[{self.name}] Story after improvement: {improved_story[:100]}...")

        # 3. Quality Checks (Grammar and Tone Analysis)
        logger.info(f"[{self.name}] Step 3: Performing quality checks")
        async for event in self.sequential_agent.run_async(ctx):
            logger.info(f"[{self.name}] QualityChecks event: {event.model_dump_json(exclude_none=True)}")
            yield event

        # 4. Conditional Logic Based on Tone Analysis
        tone_result = ctx.session.state.get("tone_check_result", "").lower()
        grammar_result = ctx.session.state.get("grammar_suggestions", "")

        logger.info(f"[{self.name}] Quality check results:")
        logger.info(f"[{self.name}] - Tone: {tone_result}")
        logger.info(f"[{self.name}] - Grammar: {grammar_result}")

        # Conditional regeneration for negative tone
        if tone_result == "negative":
            logger.info(f"[{self.name}] Step 4: Tone is negative, regenerating with more positive approach")

            # Modify the topic to encourage positive tone
            original_topic = ctx.session.state.get("topic", "")
            positive_topic = f"{original_topic} (focus on hope, resilience, and positive outcomes)"
            ctx.session.state["topic"] = positive_topic

            # Regenerate the story
            async for event in self.story_generator.run_async(ctx):
                logger.info(f"[{self.name}] StoryGenerator (regen) event: {event.model_dump_json(exclude_none=True)}")
                yield event

            # Restore original topic
            ctx.session.state["topic"] = original_topic

            final_story = ctx.session.state.get("current_story", improved_story)
            logger.info(f"[{self.name}] Regenerated story: {final_story[:100]}...")
        else:
            logger.info(f"[{self.name}] Step 4: Tone is acceptable ({tone_result}), keeping current story")

        logger.info(f"[{self.name}] Creative writing workflow completed successfully")


# --- Create the Custom Agent Instance ---

# Instantiate the custom orchestrator
root_agent = StoryFlowAgent(
    name="CreativeWritingAssistant",
    story_generator=story_generator,
    critic=critic,
    reviser=reviser,
    grammar_check=grammar_check,
    tone_check=tone_check,
)