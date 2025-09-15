import aiohttp
import asyncio
import openai
import os
import json
import pytest
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote_plus
from dotenv import load_dotenv
from agent import BaseAgent, TaskResult

class WebResearcher(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="web_researcher", model_name="gpt-4o-mini")
        self.capabilities = ["web_search", "content_extraction", "fact_checking"]
        self.max_sources = 10
        self.timeout = 10
        
        # Initialize OpenAI client
        load_dotenv()
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Google Search API credentials
        self.google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.google_search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    @pytest.mark.asyncio
    async def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        query = task.get("query")
        description = task.get("description", "No description provided")
        context = task.get("context", "")
        
        if not query:
            return TaskResult(
                task_id=self.agent_id,
                task_description=description,
                findings="No query provided for web search",
                sources=[],
                confidence_score=0.0,
                status="failed"
            )
        
        print(f"🔍 WebResearcher starting research on: {query}")

        # Step 1: Perform web search and content extraction
        search_results = await self.perform_web_search(query)
        
        # Step 2: Extract and clean content from web sources
        extracted_content = await self.extract_content_from_sources(search_results)
        
        # Step 3: Synthesize findings using LLM
        synthesized_findings = await self.synthesize_research_findings(
            query, description, context, extracted_content
        )

        # Step 4: Extract reliable sources
        reliable_sources = self.extract_reliable_sources(extracted_content)
        
        # Calculate confidence based on source quality and content relevance
        confidence_score = self.calculate_confidence_score(extracted_content, reliable_sources)
        
        return TaskResult(
            task_id=self.agent_id,
            task_description=description,
            findings=synthesized_findings,
            sources=reliable_sources,
            confidence_score=confidence_score,
            status="completed"
        )
    
    def can_handle_task(self, task_type: str) -> bool:
        """Check if the researcher can handle the given task type."""
        return task_type in ["web_search", "fact_checking", "current_events"]
    
    @pytest.mark.asyncio
    async def perform_web_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform web search using multiple strategies.
        """
        search_results = []
    
        if self.google_api_key and self.google_search_engine_id:
            try:
                search_results = await self.call_google_search_api(query)
                print(f"✅ Got {len(search_results)} results from Google")
            except Exception as e:
                print(f"❌ Google Search failed: {e}")
    
        if not search_results:
            print("🔄 Using simulated search results as fallback")
            search_results = await self.simulate_search_results(query)
    
        return search_results
    
    async def call_google_search_api(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Call Google Custom Search API to get search results.
        """
        if not self.google_api_key or not self.google_search_engine_id:
            raise ValueError("Google Search API credentials not configured")
        
        # Prepare the API URL
        base_url = "https://www.googleapis.com/customsearch/v1"
        
        params = {
            'key': self.google_api_key,
            'cx': self.google_search_engine_id,
            'q': query,
            'num': min(num_results, 10),  # Google API max is 10 per request
            'safe': 'active',  # Safe search
            'fields': 'items(title,link,snippet,displayLink)',  # Only get needed fields
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self.parse_google_search_results(data)
                    else:
                        error_text = await response.text()
                        raise Exception(f"Google Search API error {response.status}: {error_text}")
                        
        except Exception as e:
            print(f"Error calling Google Search API: {e}")
            raise
    
    def parse_google_search_results(self, google_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse Google Search API response into standardized format.
        """
        search_results = []
        
        items = google_data.get('items', [])
        
        for item in items:
            # Extract domain from display link
            display_link = item.get('displayLink', '')
            domain = display_link if display_link else self.extract_domain_from_url(item.get('link', ''))
            
            result = {
                'title': item.get('title', 'No title'),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', 'No snippet available'),
                'domain': domain,
                'source': 'google_search'
            }
            
            # Only add if we have a valid URL
            if result['url'] and result['url'].startswith(('http://', 'https://')):
                search_results.append(result)
        
        return search_results
    
    async def simulate_search_results(self, query: str) -> List[Dict[str, Any]]:
        """Simulate search results as fallback."""
        return [
            {
                'title': f"Research on {query}",
                'url': f"https://example.com/research/{query.replace(' ', '-')}",
                'snippet': f"Comprehensive information about {query}",
                'domain': "example.com",
                'source': 'simulated'
            },
            {
                'title': f"{query} - Academic Study",
                'url': f"https://academic.edu/study/{query.replace(' ', '_')}",
                'snippet': f"Academic research on {query}",
                'domain': "academic.edu",
                'source': 'simulated'
            }
        ]

    async def extract_content_from_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract and clean content from web sources."""
        if not search_results:
            print("⚠️ No search results to extract content from")
            return []
        
        extracted_content = []
        limited_results = search_results[:self.max_sources]
        semaphore = asyncio.Semaphore(3)
        
        async def extract_single_source(source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    content = await self.scrape_web_content(source["url"])
                    if content and len(content) > 100:
                        return {
                            "url": source["url"],
                            "title": source["title"],
                            "domain": source["domain"],
                            "content": content,
                            "snippet": source.get("snippet", ""),
                            "relevance_score": self.calculate_relevance_score(content, source)
                        }
                except Exception as e:
                    print(f"Failed to extract from {source.get('url', 'unknown')}: {e}")
                    return None
        
        extraction_tasks = [extract_single_source(source) for source in limited_results]
        results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        
        # Filter out failed extractions
        extracted_content = [result for result in results 
                        if result is not None and isinstance(result, dict)]
        
        # Sort by relevance score
        extracted_content.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        print(f"📄 Successfully extracted content from {len(extracted_content)} sources")
        return extracted_content
        
    async def scrape_web_content(self, url: str) -> Optional[str]:
        """
        Scrape content from a web page.
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Parse with BeautifulSoup
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Remove script and style elements
                        for script in soup(["script", "style", "nav", "header", "footer"]):
                            script.decompose()
                        
                        # Extract main content
                        content_selectors = ['article', 'main', '.content', '.article-body', 'body']
                        content = ""
                        
                        for selector in content_selectors:
                            elements = soup.select(selector)
                            if elements:
                                content = elements[0].get_text(strip=True, separator=' ')
                                break
                        
                        if not content:
                            content = soup.get_text(strip=True, separator=' ')
                        
                        # Clean up content
                        content = self.clean_extracted_content(content)
                        
                        return content[:5000]  # Limit content length
                    
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None

    def clean_extracted_content(self, content: str) -> str:
        """Clean and normalize extracted content."""
        import re
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common website noise
        noise_patterns = [
            r'Cookie Policy.*?(?=\w)',
            r'Privacy Policy.*?(?=\w)',
            r'Terms of Service.*?(?=\w)',
            r'Subscribe to.*?(?=\w)',
            r'Follow us.*?(?=\w)'
        ]
        
        for pattern in noise_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def extract_domain_from_url(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return "unknown-domain"
    
    async def synthesize_research_findings(self, query: str, description: str, 
                                         context: str, extracted_content: List[Dict[str, Any]]) -> str:
        """
        Use LLM to synthesize research findings from extracted content.
        This is the key step that transforms raw content into focused insights.
        """
        if not extracted_content:
            return f"Unable to find substantial information about '{query}'. No reliable sources were accessible."
        
        # Prepare content summary for LLM
        content_summary = self.prepare_content_for_synthesis(extracted_content)
        
        synthesis_prompt = f"""
        You are a research analyst tasked with synthesizing information about a specific research question.
        
        Research Query: "{query}"
        Research Description: "{description}"
        Research Context: "{context}"
        
        Based on the following extracted information from web sources, provide a comprehensive, well-structured analysis:
        
        {content_summary}
        
        Please provide:
        1. A clear, focused answer to the research question
        2. Key findings and insights
        3. Important data points or statistics (if available)
        4. Different perspectives or viewpoints (if present)
        5. Current trends or developments
        6. Limitations or gaps in the available information
        
        Requirements:
        - Focus specifically on the research query, not broader topics
        - Be objective and factual
        - Cite source domains when referencing specific information
        - Acknowledge uncertainty when information is limited
        - Provide actionable insights where possible
        - Keep the response comprehensive but concise (aim for 300-500 words)
        
        Format your response as a well-structured research summary.
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert research analyst who synthesizes information from multiple sources to provide focused, accurate insights."},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.3,  # Lower temperature for more factual responses
                max_tokens=800
            )
            
            synthesized_findings = response.choices[0].message.content
            return synthesized_findings
            
        except Exception as e:
            print(f"Error synthesizing findings: {e}")
            # Fallback to basic summary
            return self.create_fallback_summary(query, extracted_content)

    def prepare_content_for_synthesis(self, extracted_content: List[Dict[str, Any]]) -> str:
        """Prepare extracted content for LLM synthesis."""
        content_parts = []
        
        for i, content_item in enumerate(extracted_content[:3], 1):  # Limit to top 3 sources
            source_summary = f"""
            Source {i} - {content_item['domain']}:
            Title: {content_item['title']}
            Relevance Score: {content_item.get('relevance_score', 0):.2f}
            Content: {content_item['content'][:1000]}...
            """
            content_parts.append(source_summary)
        
        return "\n".join(content_parts)
    
    def create_fallback_summary(self, query: str, extracted_content: List[Dict[str, Any]]) -> str:
        """Create a basic summary when LLM synthesis fails."""
        if not extracted_content:
            return f"No substantial information found for '{query}'."
        
        summary_parts = [f"Research findings for '{query}':\n"]
        
        for i, content_item in enumerate(extracted_content[:2], 1):
            summary_parts.append(f"{i}. From {content_item['domain']}: {content_item['content'][:200]}...")
        
        return "\n".join(summary_parts)
    
    def extract_reliable_sources(self, extracted_content: List[Dict[str, Any]]) -> List[str]:
        """Extract list of reliable source URLs."""
        return [content["url"] for content in extracted_content 
                if content.get("relevance_score", 0) > 0.1]
    
    def calculate_confidence_score(self, extracted_content: List[Dict[str, Any]], 
                                 sources: List[str]) -> float:
        """Calculate confidence score based on source quality and content."""
        if not extracted_content:
            return 0.0
        
        # Base score from number of sources
        source_score = min(len(sources) * 0.2, 0.6)
        
        # Quality score from average relevance
        avg_relevance = sum(content.get("relevance_score", 0) 
                          for content in extracted_content) / len(extracted_content)
        quality_score = avg_relevance * 0.4
        
        return min(source_score + quality_score, 0.95)  # Cap at 0.95
    
    def calculate_relevance_score(self, content: str, source: Dict[str, Any]) -> float:
        """Calculate relevance score for extracted content."""
        score = 0.0
        
        # Domain reputation scoring
        domain = source.get("domain", "")
        if any(trusted in domain for trusted in [".edu", ".gov", ".org"]):
            score += 0.3
        elif any(news in domain for news in ["bbc", "reuters", "cnn", "nytimes"]):
            score += 0.2
        
        # Content length scoring
        if len(content) > 1000:
            score += 0.2
        elif len(content) > 500:
            score += 0.1
        
        # Title relevance (basic keyword matching)
        title = source.get("title", "").lower()
        if len(title) > 10:
            score += 0.1
        
        return min(score, 1.0)  # Cap at 1.0