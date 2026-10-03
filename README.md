# Learning to Build a Gemini Agent

This project began as a small weather-agent exercise and grew into a command-line agent that can use Python tools. Gemini runs through its API; the local Python program provides the tools and executes them.

## What This Agent Does Now

- **Weather lookup:** `get_weather(city)` asks `wttr.in` for a short report and returns it to Gemini.
- **Create project files:** `create_workspace_file(path, content)` writes Gemini-generated content under `weather-agent/workspace/`, making parent folders when needed. It asks before replacing an existing file and rejects paths outside the workspace.
- **Run Windows commands:** `run_cmd(command)` asks for approval, runs the command from the project folder, and returns its output and exit code to Gemini. Commands run with your Windows account's permissions, so inspect each one before approving it.

The command-line chat keeps conversation context while the program is running. That history is in memory and is lost when the program exits.

## LLM And Agent

An LLM receives input and generates output. An agent is a program that connects an LLM to tools and handles the tool-call cycle. The model chooses a tool and supplies arguments; Python validates or executes those arguments and returns the result to the model. In this project, Gemini does not directly write to disk or run commands; the Python tools do that.

## Example Workflow

You can ask the agent for weather or for a small project in a language or framework. For example:

```text
What is the current weather in Pune?
Create a React todo app with add, edit, complete, and delete features.
Create a Python CLI calculator with addition, subtraction, multiplication, and division.
Create a JavaScript quiz app with HTML and CSS.
```

For a project request such as "Create a React todo app":

1. The CLI sends the message and available tool descriptions to Gemini.
2. Gemini plans the project files and calls `create_workspace_file` with each relative path and its content. For example, a React project might need `todo-app/src/App.jsx` and `todo-app/package.json`.
3. Python validates each path, keeps it inside `workspace/`, creates needed parent folders, and writes the content. If replacing an existing file, it asks for approval.
4. The tool result goes back to Gemini. Gemini can create additional files or summarize the result.
5. If a command is needed to install dependencies or run a check, Gemini can request `run_cmd`; you review and approve it, and its output is returned to Gemini.

For a weather question, Gemini calls `get_weather` with the city name and uses the returned report in its response. For a Python or JavaScript project, it follows the same file-writing workflow as React; the generated files and any setup commands depend on the requested project.

## Setup

Use Python and a Gemini API key. Install the dependencies used by the current script:

```powershell
python -m pip install google-genai httpx pydantic python-dotenv
```

Store your key in a `.env` file in the project folder:

```text
GEMINI_API_KEY=your-key
```

Do not publish `.env` or share the API key. Start the CLI from the project folder:

```powershell
python weather_agent.py
```

Ask for weather or request a project in React, Python, JavaScript, or another language. Project files are created under `workspace/`. They are not automatically tested or launched; inspect them and approve an appropriate command if you want the agent to run one.

## Original Weather-Agent Walkthrough

The sections below document the simpler first version, when the project had only a weather tool. They are useful for learning the basics, but the code examples are not a complete copy of the current agent, which also has workspace-file and command tools.

## What You Will Learn

- How an LLM uses a tool provided by your program.
- How to validate a tool argument with Pydantic.
- How to keep available tools in one registry so you can add more later.
- How to run the agent as an interactive CLI.

This first version does not use FastAPI, async code, a local model, or a complicated agent framework. Once the CLI works, it is easier to add those pieces intentionally.

## 1. Create the Project

Open PowerShell in the `Agents` folder and create a project directory:

```powershell
mkdir weather-agent
cd weather-agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Create `requirements.txt` with:

```text
google-genai
httpx
pydantic
```

Install the packages:

```powershell
python -m pip install -r requirements.txt
```

`google-genai` connects to Gemini. `httpx` makes the weather request. Pydantic validates the city argument before the tool uses it.

## 2. Set Up Gemini

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey). In the same PowerShell window where you will run the agent, set the key:

```powershell
$env:GEMINI_API_KEY = "your-key"
```

The Google SDK reads this environment variable. Keep the key private; do not put it in your Python file or commit it to Git. API quotas and billing depend on your Google account, so check your current limits.

You can check the key and model with this one-line request:

```powershell
python -c "from google import genai; c=genai.Client(); print(c.models.generate_content(model='gemini-3.8-flash', contents='Reply with READY').text)"
```

If `gemini-3.8-flash` is unavailable to your account, replace it in the command and code below with a Gemini text model available to you.

## 3. Create `weather_agent.py`

Create a Python file named `weather_agent.py`. We will put the first version in one file to keep the flow visible.

### Imports and client

```python
from urllib.parse import quote

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError


client = genai.Client()
MODEL_NAME = "gemini-3.8-flash"
```

`genai.Client()` creates the connection to Gemini. The API key comes from the environment variable; it is not hard-coded here.

### Validate the tool input

Add this model below the client setup:

```python
class WeatherInput(BaseModel):
    city: str = Field(min_length=1, max_length=80)
```

The weather tool needs one value: a city name. This small Pydantic model rejects an empty or excessively long city value before it is used in a request.

### Write the weather tool

Add this function below the model:

```python
def get_weather(city: str) -> str:
    """Get a short current-weather report for a city."""
    city = city.strip()
    validated = WeatherInput(city=city)
    city_path = quote(validated.city, safe="")

    try:
        response = httpx.get(
            f"https://wttr.in/{city_path}",
            params={"format": "3"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return "The weather service could not be reached."

    return response.text.strip()
```

This is the actual Python tool. It takes a city and returns the weather service's response as a plain string. The `quote` call safely encodes city names in the URL. The function's name, type hint, and docstring also tell Gemini what the tool does and what argument it needs.

The weather service used here, `wttr.in`, accepts the city in its URL and can return a short text report. It does not need an API key. It is separate from Gemini: Gemini decides when to call our function, and this function fetches the weather.

### Create the tool registry

Add this after the function:

```python
TOOLS = [
    get_weather,
]
```

This list is the set of tools the agent is allowed to use. We pass it to Gemini in the next section. Keeping tools in one list gives us a simple place to register future capabilities.

### Ask Gemini to run the agent

Add this function:

```python
def ask_agent(user_message: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a helpful weather assistant. "
                "Use the get_weather tool for current weather questions. "
                "If the city is unclear, ask the user to clarify."
            ),
            tools=TOOLS,
        ),
    )
    return response.text or "I couldn't produce an answer."
```

The system instruction gives Gemini its role. `tools=TOOLS` makes the registered Python functions available to it. The Google GenAI SDK handles the basic function-calling cycle: Gemini can request a tool, the SDK calls the Python function, and Gemini uses the returned string to form its answer.

The model does not run the weather function by itself, and it does not get arbitrary access to your computer. Your program decides exactly which Python functions are available.

### Add the CLI loop

Finish the file with:

```python
def main() -> None:
    print("Weather agent. Type 'exit' to quit.")

    while True:
        user_message = input("You: ").strip()

        if user_message.lower() in {"exit", "quit"}:
            break

        if not user_message:
            continue

        try:
            answer = ask_agent(user_message)
            print(f"Agent: {answer}")
        except Exception as error:
            print(f"Request failed: {error}")


if __name__ == "__main__":
    main()
```

The loop lets you ask multiple questions without restarting the program. The `if __name__ == "__main__"` check runs the CLI when you launch this file directly, while still allowing its functions to be imported later.

## 4. Run and Test It

In PowerShell, from the project directory, run:

```powershell
python weather_agent.py
```

Try questions such as:

```text
What is the weather in Tokyo right now?
Tell me the current weather in London.
```

Also try a question unrelated to weather. Gemini should answer without calling the weather tool. Try `exit` to stop the CLI.

## How the Agent Flow Works

1. The CLI reads your message.
2. `ask_agent` sends it to Gemini along with the system instruction and registered tools.
3. Gemini decides whether a tool is needed. For a weather question, it supplies a city to `get_weather`.
4. The SDK calls `get_weather`, which returns a string from the weather service.
5. Gemini uses that result to write the answer shown in the CLI.

That is the small agent loop in this first version: **LLM + tools + orchestration**. The SDK hides the low-level handoff for now. You can later implement that handoff yourself to study each function-call message.

## Add More Tools Later

Write a normal Python function, give it a clear docstring and type hints, then add it to `TOOLS`. For example, a future file-listing tool might begin like this:

```python
def list_workspace_files() -> str:
    """List files in the agent's dedicated workspace folder."""
    return "Workspace file listing is not implemented yet."
```

Then register it:

```python
TOOLS = [
    get_weather,
    list_workspace_files,
]
```

You could later add specific tools such as `read_file`, `create_file`, `edit_file`, and `delete_file` in the same way. Keep them as narrow Python functions instead of giving Gemini a general Linux shell command. For file tools, restrict all paths to a dedicated folder, prevent paths such as `..` from escaping it, and require explicit confirmation before deleting or overwriting anything.

When there are enough tools to justify separate modules, move them into files such as `weather_tools.py` and `file_tools.py`, and keep a central registry that imports and lists the allowed functions. There is no need to create that structure before the first tool works.

## Pydantic and Structured Output

The first version uses Pydantic only to validate the weather tool's city input. The CLI returns normal text, so a structured JSON response is not necessary yet.

When another part of your program needs predictable fields instead of free-form text, you can add a small Pydantic response model and configure Gemini for structured output. Do that after the weather tool works; it is a separate improvement, not a requirement for understanding tool use.

## Troubleshooting

- **API key error:** Set `GEMINI_API_KEY` in the same PowerShell window where you run Python.
- **Model not found or unavailable:** Choose a Gemini text model available to your account and update `MODEL_NAME`.
- **Weather request fails:** Check your internet connection and try again; the weather service is separate from Gemini.
- **Gemini answers without weather:** Make the system instruction and `get_weather` docstring explicit that the tool provides current conditions.