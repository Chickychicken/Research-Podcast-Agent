import asyncio
from typing import Dict, Any, List, Optional
from supervisor import Supervisor
from web_researcher import WebResearcher
from reporter import Reporter
from speaker import Speaker

class DeepResearchSystem:
    def __init__(self):
        self.supervisor = Supervisor()
        self.reporter = Reporter()
        self._setup_agents()
    
    def _setup_agents(self):
        """Initialize and add agents to the supervisor."""
        web_researcher = WebResearcher()
        self.supervisor.add_sub_agent(web_researcher)
        
        print(f"✅ System initialized with {len(self.supervisor.sub_agents)} agents")
    
    async def conduct_web_research(self, topic: str, research_brief: str = None) -> str:
        """
        Main entry point for comprehensive research process.
        
        Args:
            topic: The research topic
            research_brief: Optional detailed research requirements
            
        Returns:
            Comprehensive research report
        """
        print(f"🚀 Starting research on: '{topic}'")
        
        try:
            # Step 1: Get follow-up questions from supervisor
            print("📋 Planning research strategy...")
            questions, question_message = await self.supervisor.generate_follow_up_questions(topic)
            
            # Display questions to the user
            print("\n" + question_message)
            
            # Collect user responses
            user_responses = []
            for i, question in enumerate(questions, 1):
                response = input(f"Your answer to question {i}: ")
                user_responses.append(response)
            
            # Create additional context from user responses
            additional_context = "\nUser responses to follow-up questions:\n"
            for i, (question, response) in enumerate(zip(questions, user_responses), 1):
                additional_context += f"Q{i}: {question}\nA{i}: {response}\n\n"
            
            # Now plan research with the enhanced context
            tasks = await self.supervisor.plan_research(topic, additional_context)
            print(f"📝 Created {len(tasks)} research tasks")
            
            # Step 2: Execute tasks - Delegate to sub-agents
            print("🔍 Executing research tasks...")
            results = await self.supervisor.delegate_tasks(tasks)
            print(f"✅ Completed {len(results)} research tasks")
            
            # Step 3: Generate comprehensive report
            print("📊 Generating final report...")
            report = await self.reporter.generate_report(topic, results, research_brief)
            
            print("🎉 Research completed successfully!")
            return report
            
        except Exception as e:
            print(f"❌ Research failed: {e}")
            # Return error report
            return await self._generate_error_report(topic, str(e))
    
    async def get_research_status(self) -> Dict[str, Any]:
        """Get current system status and capabilities."""
        return {
            "system_status": "operational",
            "total_agents": len(self.supervisor.sub_agents),
            "agent_types": [agent.__class__.__name__ for agent in self.supervisor.sub_agents],
            "agent_capabilities": [agent.capabilities for agent in self.supervisor.sub_agents],
            "supervisor_config": {
                "max_parallel_tasks": self.supervisor.max_parallel_tasks,
                "task_queue_size": len(self.supervisor.task_queue)
            },
            "reporter_model": self.reporter.model_name
        }
    
    async def _generate_error_report(self, topic: str, error_message: str) -> str:
        """Generate error report when research fails."""
        return f"""
        # Research Report: {topic}
        
        ## Status: Failed
        
        Unfortunately, the research process encountered an error and could not complete.
        
        **Error Details:**
        {error_message}
        
        ## Recommendations:
        - Check your API keys and network connection
        - Verify that all required dependencies are installed
        - Try using a more specific research topic
        - Contact system administrator if the problem persists
        """

async def main():
    """Main function to run deep research."""
    print("🔬 Deep Research Tool")
    print("="*40)
    
    try:
        system = DeepResearchSystem()
        
        topic = input("Enter research topic: ").strip()
        if not topic:
            print("❌ Error: Research topic cannot be empty")
            return
            
        report = await system.conduct_web_research(topic)
        
        # Save report to file
        filename = f"research_report_{topic.replace(' ', '_')[:30]}.txt"
        with open(filename, "w") as f:
            f.write(report)
            
        print(f"📄 Full report saved to {filename}")
        print(f"📊 Report length: {len(report)} characters")

        # Create podcast from report
        print("\n🎙️ Converting report to podcast format...")
        speaker = Speaker()
        audio_path = await speaker.create_podcast_from_report(
            report=report,
            topic_name=topic,
            play_audio=True  # We will ask user if they want to play it later
        )
        
        print(f"🎵 Podcast created at: {audio_path}")
        
        # Ask if user wants to save the podcast permanently
        save_response = input("\nWould you like to keep this podcast file? (y/n): ").strip().lower()
        if save_response != 'y':
            try:
                import os
                os.remove(audio_path)
                print(f"🗑️ Podcast file deleted")
            except Exception as e:
                print(f"⚠️ Could not delete podcast file: {e}")
        
    except Exception as e:
        print(f"❌ System error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())