from urllib.parse import quote
import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
from pathlib import Path
import subprocess

load_dotenv()

client = genai.Client()
MODEL_NAME = 'gemini-3.5-flash-lite'
PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR / 'workspace'

#Validation
class WeatherInput(BaseModel):
    city:str = Field(min_length=1, max_length=80)

class WorkspaceFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=100_000)


def create_workspace_file(path: str, content: str) -> str:
    """Create or update one file inside workspace; ask before replacing it."""
    try:
        file_input = WorkspaceFileInput(path=path, content=content)
        relative_path = Path(file_input.path)
        if relative_path.is_absolute() or relative_path.drive:
            return 'Use a relative path inside workspace.'

        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        workspace_root = WORKSPACE_DIR.resolve()
        file_path = (workspace_root / relative_path).resolve()
        if file_path == workspace_root or workspace_root not in file_path.parents:
            return 'That path is outside workspace.'

        if file_path.exists():
            if not file_path.is_file():
                return 'That path exists but is not a file.'
            print(f'The agent wants to replace workspace/{file_path.relative_to(workspace_root)}')
            if input('Replace it? Type yes to approve: ').strip().lower() != 'yes':
                return 'File update cancelled.'

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_input.content, encoding='utf-8')
        return f'Wrote workspace/{file_path.relative_to(workspace_root)} ({len(file_input.content)} characters).'
    except (OSError, ValueError) as error:
        return f'Could not write the file: {error}'


def run_cmd(command: str) -> str:
    """Run an approved Windows command and return its output to the agent."""
    if not command.strip():
        return 'No command was provided.'

    print(f'The agent wants to run:\n{command}')
    if input('Run this command? Type yes to approve: ').strip().lower() != 'yes':
        return 'Command cancelled.'

    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return 'Command timed out after 30 seconds.'

    output = '\n'.join(part for part in (result.stdout, result.stderr) if part).strip()
    if len(output) > 4000:
        output = output[-4000:]
    return f'Exit code: {result.returncode}\n{output or "(no output)"}'

    

#get weather tool
def get_weather(city:str) -> str:
    """Get a short current-weather report for a city."""
    print(f'user shared city name: {city}')
    city = city.strip().lower()
    validated = WeatherInput(city=city)
    city_path = quote(validated.city, safe='') #quote call safely encoded city name in url.
    try:
        response = httpx.get(
            f'https://wttr.in/{city_path}"',
            params={'format': '3'}, # it gets attach in url which tells to return one short line weather report
            timeout= 10
            )
        response.raise_for_status()
    except httpx.HTTPError:
        return 'The weather service could not be reached.'
    return response.text.strip()


# Set of tools agent is allowed to use
TOOLS = [
    get_weather,
    create_workspace_file,
    run_cmd,
]

chat = client.chats.create(
    model=MODEL_NAME,
    config=types.GenerateContentConfig(
        system_instruction=(
            'You are a helpful assistant. Use get_weather for current weather. '
            'When creating an app, use create_workspace_file to write each file '
            'under workspace, with relative paths such as todo/index.html. '
            'That tool creates parent folders. Do not use shell echo commands '
            'to write source code. Use run_cmd only for approved Windows '
            'commands such as listing files or running checks. Commands run '
            'from the project folder. Only report success when a tool confirms it.'
        ),
        tools=TOOLS,
    ),
)

def ask_agent(user_message:str)->str:
    response = chat.send_message(user_message)
    return response.text or 'I could not produce an answer.'


def main():
    print("Weather agent. Type 'exit' to quit. ")

    while True:
        user_message = input("You: ").strip()

        if user_message.lower() in {"quit", "exit"}:
            break

        if not user_message:
            continue

        try:
            answer = ask_agent(user_message)
            print(f'Agent: {answer}')
        except Exception as error:
            print(f'Request failed: {error}')


if __name__ == "__main__":
    main()