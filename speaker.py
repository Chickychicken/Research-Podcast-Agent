import os
import re
import time
import shutil
import platform
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

# --- Main Speaker Class ---

class Speaker:
    """
    A class to convert research reports into podcasts using AI for both
    scripting and text-to-speech.
    """
    def __init__(self):
        load_dotenv()
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        # CHANGED: Initialize the async client
        self.client = AsyncOpenAI(api_key=openai_api_key) 
        
        self.voice_name = "nova"  # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
        self.output_directory = "podcasts"
        self.max_chunk_size = 4000  # OpenAI TTS character limit
        
        os.makedirs(self.output_directory, exist_ok=True)

    async def create_podcast_from_report(self, report: str, topic_name: str, play_audio: bool = False):
        """
        Main function to convert a report into a multi-part podcast.

        This function orchestrates the entire process:
        1. Uses GPT-4o-mini to edit the report into a conversational podcast script.
        2. Converts that script into a series of audio files (chunks).
        
        Args:
            report (str): The full research report text.
            topic_name (str): The main topic, used for naming files and folders.
            play_audio (bool): Whether to play the first audio chunk after creation.
        
        Returns:
            str: The path to the directory containing the podcast audio files.
        """
        print(f"🎙️ Starting podcast creation for topic: '{topic_name}'")

        # 1. Edit the report into a podcast script using an AI model
        print("✍️  Rewriting report into a podcast script with GPT-4o-mini...")
        try:
            podcast_script = await self._edit_report_for_podcast(report, topic_name)
        except Exception as e:
            print(f"❌ Error editing report with AI: {e}")
            return None

        # 2. Convert the generated script to audio chunks
        print("🗣️  Converting script to audio...")
        try:
            output_path = self._convert_text_to_audio(podcast_script, topic_name)
            print(f"✅ Successfully created podcast files in: {output_path}")
        except Exception as e:
            print(f"❌ Error converting text to audio: {e}")
            return None

        # 3. Play the first audio chunk if requested
        if play_audio and output_path:
            first_chunk = os.path.join(output_path, "part_1.mp3")
            if os.path.exists(first_chunk):
                self.play_audio(first_chunk)
            else:
                print("Could not find the first audio chunk to play.")
        
        return output_path

    async def _edit_report_for_podcast(self, report: str, topic_name: str) -> str:
        """
        Uses a chat model to rewrite a formal report into an engaging podcast script.
        """
        system_prompt = """
        You are an expert podcast scriptwriter. Your task is to transform a formal, dense research report into an engaging, conversational, and easy-to-understand podcast script.

        Follow these instructions:
        - Start with a catchy and welcoming introduction.
        - End with a clear and concise outro, thanking the listener.
        - Convert complex data, findings, and recommendations into a natural, narrative format. Use analogies where helpful.
        - Do not just summarize. Rewrite and rephrase the content to be spoken.
        - Keep the core facts, data, and insights from the original report.
        - Structure the script with clear sections, but use conversational transitions instead of formal headers.
        """
        
        user_prompt = f"Please rewrite the following research report on the topic '{topic_name}' into a podcast script:\n\n--- REPORT START ---\n{report}\n--- REPORT END ---"

        # This 'await' now works correctly with the AsyncOpenAI client
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content

    def _convert_text_to_audio(self, text: str, topic_name: str) -> str:
        """
        Converts a long string of text into multiple, numbered MP3 files.
        """
        # Create a unique directory for this podcast's audio chunks
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_topic = "".join(c if c.isalnum() else "_" for c in topic_name)
        podcast_dir = os.path.join(self.output_directory, f"{clean_topic}_{timestamp}")
        os.makedirs(podcast_dir, exist_ok=True)

        chunks = self._split_into_chunks(text, self.max_chunk_size)
        print(f"   > Script split into {len(chunks)} audio parts.")

        # Note: _generate_speech is synchronous, which is fine to call from an async function
        for i, chunk in enumerate(chunks):
            chunk_filename = os.path.join(podcast_dir, f"part_{i+1}.mp3")
            print(f"   > Generating {chunk_filename}...")
            try:
                self._generate_speech(chunk, chunk_filename)
            except Exception as e:
                print(f"   > ❗ Failed to generate part {i+1}: {e}")
        
        return podcast_dir

    def _generate_speech(self, text: str, output_file: str):
        """Generates a single MP3 file from a text chunk using OpenAI TTS."""
        try:
            # The standard client can be used for synchronous operations like TTS
            sync_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = sync_client.audio.speech.create(
                model="tts-1",
                voice=self.voice_name,
                input=text,
            )
            response.stream_to_file(output_file)
            time.sleep(1)  # Small delay to respect API rate limits
        except Exception as e:
            # Propagate the error to be handled by the calling function
            raise e

    def _split_into_chunks(self, text: str, max_length: int) -> list[str]:
        """Splits text into chunks by sentences, respecting the max_length."""
        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', text.replace("\n", " "))
        
        current_chunk = ""
        for sentence in sentences:
            if not sentence: continue
            if len(current_chunk) + len(sentence) + 1 > max_length and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
            else:
                current_chunk += sentence + " "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    def set_voice(self, voice_name: str = 'nova'):
        """Changes the TTS voice."""
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        if voice_name in valid_voices:
            self.voice_name = voice_name
            print(f"Voice set to '{self.voice_name}'")
        else:
            print(f"Invalid voice name. Using '{self.voice_name}'.")

    def play_audio(self, audio_path: str):
        """Plays an audio file using the system's default player."""
        if not os.path.exists(audio_path):
            print(f"Error: Audio file not found at {audio_path}")
            return
            
        print(f"🔊 Playing audio: {os.path.basename(audio_path)}")
        system = platform.system()
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["afplay", audio_path], check=True)
            elif system == "Windows":
                os.startfile(audio_path)
            elif system == "Linux":
                subprocess.run(["xdg-open", audio_path], check=True)
            else:
                print(f"Unsupported OS '{system}'. Please play file manually.")
        except Exception as e:
            print(f"Error playing audio: {e}")

# --- Testing Speaker ---
if __name__ == "__main__":
    import asyncio

    # Example of a research report
    with open("test.txt", "r") as f:
            dummy_report = f.read()
    print(f"✅ Loaded test content ({len(dummy_report)} characters)")
    
    async def main():
        # Initialize the speaker
        speaker = Speaker()
        
        # Set a voice you like
        speaker.set_voice("nova")
        
        # Create the podcast
        # The result will be a folder with numbered audio files.
        await speaker.create_podcast_from_report(
            report=dummy_report,
            topic_name="The Future of Remote Work",
            play_audio=True  # Will play part_1.mp3
        )

    # Run the asynchronous main function
    asyncio.run(main())