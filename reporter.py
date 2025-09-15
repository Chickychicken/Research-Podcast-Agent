import openai
import os
from typing import List
from dotenv import load_dotenv
from agent import TaskResult

class Reporter:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name
        
        # Initialize OpenAI client
        load_dotenv()
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_report(self, topic: str, results: List[TaskResult], 
                            research_brief: str = None) -> str:
        """
        Generate a comprehensive report using LLM synthesis.
        
        Args:
            topic: The main research topic
            results: List of TaskResult objects from sub-agents
            research_brief: Optional detailed research brief/requirements
        """
        if not results:
            return await self._generate_empty_report(topic, research_brief)
        
        # Prepare research findings for LLM synthesis
        synthesized_findings = self._prepare_findings_for_synthesis(results)
        
        # Generate the final report using LLM
        final_report = await self._synthesize_final_report(
            topic, research_brief, synthesized_findings, results
        )
        
        return final_report
    
    def _prepare_findings_for_synthesis(self, results: List[TaskResult]) -> str:
        """
        Organize and structure research findings for LLM consumption.
        """
        findings_sections = []
        
        for i, result in enumerate(results, 1):
            # Only include completed results with substantial findings
            if result.status == "completed" and result.findings:
                section = f"""
                Research Finding #{i}:
                Focus Area: {result.task_description}
                Confidence Level: {result.confidence_score:.2f}
                
                Key Insights:
                {result.findings}
                
                Sources Referenced:
                {self._format_sources(result.sources)}
                
                ---
                """
                findings_sections.append(section)
        
        if not findings_sections:
            return "No substantial research findings were collected from sub-agents."
        
        return "\n".join(findings_sections)
    
    def _format_sources(self, sources: List[str]) -> str:
        """Format source URLs in a clean, readable way."""
        if not sources:
            return "• No sources provided"
        
        formatted_sources = []
        for i, source in enumerate(sources[:5], 1):  # Limit to top 5 sources
            # Extract domain for cleaner display
            try:
                from urllib.parse import urlparse
                domain = urlparse(source).netloc
                formatted_sources.append(f"• [{domain}]({source})")
            except:
                formatted_sources.append(f"• {source}")
        
        return "\n".join(formatted_sources)
    
    async def _synthesize_final_report(self, topic: str, research_brief: str, 
                                     synthesized_findings: str, results: List[TaskResult]) -> str:
        """
        Use LLM to create final comprehensive report.
        """
        # Calculate overall research quality metrics
        avg_confidence = self._calculate_average_confidence(results)
        total_sources = sum(len(result.sources) for result in results)
        completed_tasks = len([r for r in results if r.status == "completed"])
        
        # Construct the synthesis prompt
        synthesis_prompt = f"""
        You are an expert research analyst tasked with writing a comprehensive research report.
        
        RESEARCH TOPIC: "{topic}"
        
        RESEARCH BRIEF: {research_brief or "Provide a comprehensive analysis of the given topic."}
        
        RESEARCH FINDINGS FROM SUB-AGENTS:
        {synthesized_findings}
        
        RESEARCH QUALITY METRICS:
        - Average Confidence Score: {avg_confidence:.2f}/1.0
        - Total Sources Consulted: {total_sources}
        - Research Tasks Completed: {completed_tasks}/{len(results)}
        
        Please write a comprehensive research report that:
        
        1. **EXECUTIVE SUMMARY**: Provide a clear, concise overview of key findings (2-3 paragraphs)
        
        2. **DETAILED ANALYSIS**: 
           - Synthesize all research findings into coherent insights
           - Address the specific requirements in the research brief
           - Present multiple perspectives where available
           - Highlight key data points and statistics
           - Identify patterns and trends across sources
        
        3. **KEY FINDINGS**: List the most important discoveries and insights
        
        4. **IMPLICATIONS & RECOMMENDATIONS**: 
           - What do these findings mean?
           - Actionable recommendations based on the research
           - Future considerations or areas for further investigation
        
        5. **RESEARCH LIMITATIONS**: 
           - Acknowledge gaps in the research
           - Note areas where information was limited or conflicting
           - Suggest areas for additional research
        
        6. **SOURCES & METHODOLOGY**: 
           - Brief overview of research methodology
           - Note on source reliability and diversity
        
        FORMATTING REQUIREMENTS:
        - Use clear headings and subheadings
        - Write in professional, academic tone
        - Ensure logical flow between sections
        - Include specific citations to source domains when referencing data
        - Aim for 800-1200 words total
        - Be objective and evidence-based
        
        IMPORTANT: Base your analysis strictly on the provided research findings. Do not add information not present in the research data. If information is limited, acknowledge this explicitly.
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert research analyst who synthesizes complex information into clear, actionable reports. You are thorough, objective, and evidence-based in your analysis."
                    },
                    {
                        "role": "user", 
                        "content": synthesis_prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent, factual output
                max_tokens=2000   # Allow for comprehensive reports
            )
            
            synthesized_report = response.choices[0].message.content
            
            # Add metadata footer
            metadata_footer = self._generate_metadata_footer(results)
            
            return f"{synthesized_report}\n\n{metadata_footer}"
            
        except Exception as e:
            print(f"Error generating LLM report: {e}")
            # Fallback to basic structured report
            return await self._generate_fallback_report(topic, results)
    
    def _calculate_average_confidence(self, results: List[TaskResult]) -> float:
        """Calculate average confidence score across all results."""
        if not results:
            return 0.0
        
        valid_results = [r for r in results if r.confidence_score is not None]
        if not valid_results:
            return 0.0
        
        return sum(r.confidence_score for r in valid_results) / len(valid_results)
    
    def _generate_metadata_footer(self, results: List[TaskResult]) -> str:
        """Generate metadata footer with research statistics."""
        total_sources = sum(len(result.sources) for result in results)
        completed_tasks = len([r for r in results if r.status == "completed"])
        avg_confidence = self._calculate_average_confidence(results)
        
        return f"""
        ---
        **Research Metadata**
        - Research Tasks Completed: {completed_tasks}/{len(results)}
        - Total Sources Analyzed: {total_sources}
        - Average Confidence Score: {avg_confidence:.2f}/1.0
        - Report Generated: {self._get_current_timestamp()}
        """
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp for report metadata."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    async def _generate_empty_report(self, topic: str, research_brief: str = None) -> str:
        """Generate report when no research results are available."""
        return f"""
        # Research Report: {topic}
        
        ## Executive Summary
        Unfortunately, no research findings were available to analyze for the topic "{topic}".
        
        ## Research Brief
        {research_brief or "No specific research brief provided."}
        
        ## Status
        The research process was unable to gather sufficient information to provide meaningful insights on this topic.
        
        ## Recommendations
        - Verify that research agents are properly configured
        - Consider refining the research query or approach
        - Check if the topic requires specialized research methods
        
        ---
        **Research Metadata**
        - Research Tasks Completed: 0/0
        - Total Sources Analyzed: 0
        - Report Generated: {self._get_current_timestamp()}
        """
    
    async def _generate_fallback_report(self, topic: str, results: List[TaskResult]) -> str:
        """Generate basic structured report when LLM synthesis fails."""
        report_sections = [
            f"# Research Report: {topic}\n",
            "## Executive Summary",
            f"This report presents research findings on '{topic}' gathered from {len(results)} research tasks.\n",
            "## Research Findings\n"
        ]
        
        for i, result in enumerate(results, 1):
            if result.status == "completed":
                section = f"""
                ### Finding #{i}: {result.task_description}
                **Confidence Score:** {result.confidence_score:.2f}
                
                {result.findings}
                
                **Sources:** {', '.join(result.sources[:3]) if result.sources else 'No sources available'}
                
                ---
                """
                report_sections.append(section)
        
        # Add metadata
        report_sections.append(self._generate_metadata_footer(results))
        
        return "\n".join(report_sections)
    
    async def generate_quick_summary(self, topic: str, results: List[TaskResult]) -> str:
        """
        Generate a quick summary report (useful for intermediate updates).
        """
        if not results:
            return f"No research findings available for '{topic}' yet."
        
        completed = [r for r in results if r.status == "completed"]
        summary_parts = [
            f"Research Progress for '{topic}':",
            f"• Completed Tasks: {len(completed)}/{len(results)}",
            f"• Average Confidence: {self._calculate_average_confidence(completed):.2f}",
            f"• Total Sources: {sum(len(r.sources) for r in completed)}",
            "\nKey Findings:"
        ]
        
        for result in completed[:3]:  # Show top 3 findings
            summary_parts.append(f"• {result.task_description}: {result.findings[:100]}...")
        
        return "\n".join(summary_parts)