import pytest
import asyncio
from typing import List, Dict, Any, Tuple
from agent import BaseAgent, TaskResult
import openai
import os
from dotenv import load_dotenv

class Supervisor(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="supervisor", model_name="gpt-o4-mini")
        self.sub_agents = []
        self.task_queue = []
        self.max_parallel_tasks = 10
        
        # Add this - Initialize OpenAI client
        load_dotenv()
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def add_sub_agent(self, agent: BaseAgent):
        """Add a sub-agent to the supervisor."""
        self.sub_agents.append(agent)
    
    @pytest.mark.asyncio
    async def plan_research(self, research_topic: str, additional_context: str = "") -> List[Dict[str, Any]]:
        """
        Break down research topic into independent sub-tasks.
        Uses LLM to analyze complexity and create parallel research paths.
        """
        # If additional_context is provided, use it directly
        # Otherwise, generate follow-up questions to gather context
        if not additional_context:
            _, question_message = await self.generate_follow_up_questions(research_topic)
            enhanced_context = f"{research_topic}\n\nAdditional context/questions to consider:\n{question_message}"
        else:
            enhanced_context = f"{research_topic}\n\n{additional_context}"
        
        sub_topics = await self.analyze_and_break_down_topic(research_topic, enhanced_context)
        tasks = []
        for i, sub_topic in enumerate(sub_topics):
            task = {
                "task_id": f"research_task_{i+1}",
                "type": "web_search",  # Default to web search for now
                "query": sub_topic["query"],
                "description": sub_topic["description"],
                "context": sub_topic["context"],
                "priority": sub_topic.get("priority", "medium"),
                "sources": []
            }
            tasks.append(task)
        
        self.task_queue = tasks
        return tasks
    
    async def generate_follow_up_questions(self, research_topic: str) -> Tuple[List[str], str]:
        """
        Generate 3 follow-up questions to gather more context about the research topic.
        Returns both the list of questions and a formatted message containing the questions.
        """
        prompt = f"""
        Based on this research topic: "{research_topic}"
        
        Generate exactly 3 follow-up questions that would help gather more context and clarify:
        
        IMPORTANT: Respond ONLY with valid JSON in this exact format:
        {{
            "questions": [
                "First follow-up question?",
                "Second follow-up question?",
                "Third follow-up question?"
            ],
            "explanation": "Brief explanation of why these questions are important for this research"
        }}
        """
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a research planning expert. Respond ONLY with valid JSON. No additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Clean the response - remove any markdown formatting
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON response
            import json
            question_data = json.loads(response_text)
            questions = question_data.get("questions", [])
            explanation = question_data.get("explanation", "")
            
            # Format questions into a message
            question_message = "To better focus the research, please consider these follow-up questions:\n\n"
            for i, question in enumerate(questions, 1):
                question_message += f"{i}. {question}\n"
            question_message += f"\n{explanation}"
            
            return questions, question_message
            
        except Exception as e:
            print(f"Error generating follow-up questions: {e}")
            fallback_questions = [
                f"What specific aspects of {research_topic} are you most interested in?",
                f"Are there any time constraints or geographic focus for this research on {research_topic}?",
                f"What is the primary goal or outcome you hope to achieve with this research?"
            ]
            fallback_message = "To better focus the research, please consider these follow-up questions:\n\n"
            for i, question in enumerate(fallback_questions, 1):
                fallback_message += f"{i}. {question}\n"
            
            return fallback_questions, fallback_message

    @pytest.mark.asyncio
    async def delegate_tasks(self, tasks: List[Dict[str, Any]]) -> List[TaskResult]:
        """
        Efficiently delegate tasks to sub-agents with parallelization.
        Groups tasks by type and executes them concurrently.
        """
        if not tasks:
            return []
        
        task_groups = self.group_tasks_by_type(tasks)

        all_results = []
        for task_type, task_list in task_groups.items():
            capable_agents = []
            for agent in self.sub_agents:
                if agent.can_handle_task(task_type):
                    capable_agents.append(agent)

            if capable_agents:
                results = await self.execute_tasks_parallel(task_list, capable_agents)
                all_results.extend(results)
            else:
                print(f"Warning: No agents available for task type '{task_type}'")

        print(self.get_research_summary())
        return all_results
        
    async def analyze_and_break_down_topic(self, research_topic: str, enhanced_context: str = "") -> List[Dict[str, Any]]:
        """
        Use LLM to analyze the research topic and intelligently break it down.
        Now includes additional context from follow-up questions.
        """
        complexity_analysis = await self.analyze_topic_complexity(research_topic, enhanced_context)

        if complexity_analysis["is_complex"]:
            # If complex, break down into sub-topics
            sub_topics = await self.generate_subtopics(research_topic, complexity_analysis, enhanced_context)
        else:
            # It simple, single research task
            sub_topics = [{
                "query": research_topic,
                "description": f"Comprehensive research on {research_topic}",
                "context": enhanced_context if enhanced_context else "provide a thorough overview of the topic",
                "priority": "high"
            }]
        
        return sub_topics

    async def analyze_topic_complexity(self, research_topic: str, enhanced_context: str = "") -> Dict[str, Any]:
        """Ask LLM to determine if a topic is complex and how to approach it."""
        context_text = f"\nAdditional Context: {enhanced_context}" if enhanced_context else ""
        
        prompt = f"""
        Analyze this research topic for complexity and research strategy:
        
        Topic: "{research_topic}"{context_text}
        
        Please evaluate:
        1. What are the main aspects/dimensions of this topic?
        2. How many sub-research areas would be optimal (between 1-10)?
        3. What type of research approach would work best?
        
        IMPORTANT: Respond ONLY with valid JSON in this exact format:
        {{
            "is_complex": true,
            "main_aspects": ["aspect1", "aspect2"],
            "recommended_subtopics": <integer between 1 and 10>,
            "research_approach": "analytical",
            "reasoning": "explanation here"
        }}
        """
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a research planning expert. Respond ONLY with valid JSON. No additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1  # Very low temperature for consistent JSON
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Clean the response - remove any markdown formatting
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON response
            import json
            analysis = json.loads(response_text)

            # Print out the specific results you requested
            print("\n----- Topic Analysis Results -----")
            print(f"Main Aspects: {analysis.get('main_aspects', [])}")
            print(f"Recommended Subtopics: {analysis.get('recommended_subtopics', 0)}")
            print(f"Research Approach: {analysis.get('research_approach', 'N/A')}")
            print(f"Reasoning: {analysis.get('reasoning', 'N/A')}")
            print("--------------------------------\n")

            return analysis
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in complexity analysis: {e}")
            print(f"Raw response: {response_text}")
            # Return fallback
            return self._get_fallback_complexity_analysis(research_topic)
        except Exception as e:
            print(f"Error analyzing topic complexity: {e}")
            return self._get_fallback_complexity_analysis(research_topic)

    def _get_fallback_complexity_analysis(self, research_topic: str) -> Dict[str, Any]:
        """Fallback complexity analysis when LLM fails."""
        return {
            "is_complex": len(research_topic.split()) > 3,
            "main_aspects": [research_topic],
            "recommended_subtopics": 1,
            "research_approach": "exploratory",
            "reasoning": "Fallback analysis due to LLM error"
        }
    
    async def generate_subtopics(self, research_topic: str, complexity_analysis: Dict[str, Any], 
                               enhanced_context: str = "") -> List[Dict[str, Any]]:
        """Use LLM to generate specific sub-research topics with context."""
        num_subtopics = complexity_analysis.get("recommended_subtopics", self.max_parallel_tasks)
        main_aspects = complexity_analysis.get("main_aspects", [])
        
        context_text = f"\nAdditional Context: {enhanced_context}" if enhanced_context else ""

        prompt = f"""
        Create {num_subtopics} focused research sub-topics for: "{research_topic}"{context_text}
        
        Main aspects to cover: {main_aspects}
        Research approach: {complexity_analysis.get('research_approach', 'comprehensive')}
        
        IMPORTANT: Respond ONLY with valid JSON in this exact format:
        {{
            "subtopics": [
                {{
                    "query": "specific search terms",
                    "description": "what this sub-research focuses on",
                    "context": "specific angle or focus area",
                    "priority": "high",
                    "rationale": "why this subtopic is important"
                }}
            ]
        }}
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a research strategy expert. Respond ONLY with valid JSON. No additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Clean the response
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            import json
            subtopic_data = json.loads(response_text)
            return subtopic_data["subtopics"]
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in subtopic generation: {e}")
            print(f"Raw response: {response_text}")
            return self._get_fallback_subtopics(research_topic)
        except Exception as e:
            print(f"Error generating subtopics: {e}")
            return self._get_fallback_subtopics(research_topic)

    def _get_fallback_subtopics(self, research_topic: str) -> List[Dict[str, Any]]:
        """Fallback subtopic generation when LLM fails."""
        return [{
            "query": research_topic,
            "description": f"Research on {research_topic}",
            "context": "comprehensive overview",
            "priority": "high",
            "rationale": "Fallback single topic due to LLM error"
        }]

    def group_tasks_by_type(self, tasks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group tasks by their type for efficient agent assignment."""
        task_groups = {}
        for task in tasks:
            task_type = task.get("type", "unknown")
            if task_type not in task_groups:
                task_groups[task_type] = []
            task_groups[task_type].append(task)
        
        return task_groups

    async def execute_tasks_parallel(self, tasks: List[Dict[str, Any]], agents: List[BaseAgent]) -> List[TaskResult]:
        """
        Execute tasks in parallel using available agents.
        Implements load balancing across agents.
        """
        if not tasks or not agents:
            return []
        
        # Limit concurrent tasks to prevent overwhelming
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)
        
        async def execute_single_task(task: Dict[str, Any], agent: BaseAgent) -> TaskResult:
            async with semaphore:
                try:
                    print(f"Agent {agent.agent_id} executing: {task.get('description', 'Unknown task')}")
                    result = await agent.execute_task(task)
                    return result
                except Exception as e:
                    # Handle agent failures gracefully
                    return TaskResult(
                        task_id=task.get("task_id", "failed_task"),
                        task_description=task.get("description", "Failed task"),
                        findings=f"Task failed with error: {str(e)}",
                        sources=[],
                        confidence_score=0.0,
                        status="failed"
                    )
        
        # Distribute tasks across agents (round-robin, sequential manner)
        task_assignments = []
        for i, task in enumerate(tasks):
            agent = agents[i % len(agents)]  # Round-robin assignment
            task_assignments.append(execute_single_task(task, agent))
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*task_assignments, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        valid_results = [result for result in results 
                        if isinstance(result, TaskResult)]
        
        return valid_results
    
    # Required abstract methods from BaseAgent
    async def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """
        Supervisor doesn't execute tasks directly - it delegates them.
        This method handles meta-tasks like coordination.
        """
        if task.get("type") == "coordinate_research":
            # Handle research coordination
            topic = task.get("query", "Unknown topic")
            
            # Generate follow-up questions (in a real application, you would collect answers)
            _, question_message = await self.generate_follow_up_questions(topic)
            enhanced_context = f"{topic}\n\n{question_message}"
            
            subtasks = await self.plan_research(topic, enhanced_context)
            results = await self.delegate_tasks(subtasks)
            
            # Summarize coordination results
            findings = f"Coordinated research on '{topic}' with {len(subtasks)} sub-tasks. " \
                      f"Collected {len(results)} results from sub-agents."
            
            return TaskResult(
                task_id=self.agent_id,
                task_description=f"Coordinated research on {topic}",
                findings=findings,
                sources=[],
                confidence_score=0.9,
                status="completed"
            )
        else:
            return TaskResult(
                task_id=self.agent_id,
                task_description="Unsupported supervisor task",
                findings="Supervisor only handles coordination tasks",
                sources=[],
                confidence_score=0.0,
                status="unsupported"
            )
        
    def can_handle_task(self, task_type: str) -> bool:
        """Supervisor only handles coordination tasks."""
        return task_type in ["coordinate_research", "plan_research", "delegate_tasks"]
    
    def get_research_summary(self) -> Dict[str, Any]:
        """Get summary of current research status."""
        return {
            "total_agents": len(self.sub_agents),
            "queued_tasks": len(self.task_queue),
            "agent_capabilities": [agent.capabilities for agent in self.sub_agents],
            "max_parallel_tasks": self.max_parallel_tasks
        }