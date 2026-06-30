# Simple Coding Agent

A small terminal-based coding agent that uses `Ollama` to create, read, and modify code files inside a selected workspace folder.

## What it does

- Asks for a workspace folder before any file operation
- Stays inside the selected workspace folder
- Creates a new code file from a natural-language prompt
- Picks a file name and extension automatically
- Reads an existing code file
- Modifies an existing code file
- Creates a timestamped backup before modifying a file
- Shows clear terminal errors for common problems

## Requirements

- Windows, macOS, or Linux
- Python 3.10+
- [Ollama](https://ollama.com/)
- A pulled Ollama model, for example `qwen2.5-coder:1.5b`

## Setup

1. Install Ollama.
2. Pull a model:

```powershell
ollama pull qwen2.5-coder:1.5b
```

3. Run the agent:

```powershell
python agent.py
```

## Interactive usage

When you run `python agent.py`, the agent will:

1. Ask for a workspace folder
2. Ask for a natural-language request
3. Use Ollama to decide whether the request means create, read, or modify
4. Perform the file operation inside the workspace only
5. Print the result in the terminal

Type `exit` or `quit` to stop.

## One-shot usage

You can also run a single request directly from the terminal:

```powershell
python agent.py --workspace 'C:\path\to\workspace' --request 'Create a Python file that prints Hello World.'
python agent.py --workspace 'C:\path\to\workspace' --request 'Read main.py'
python agent.py --workspace 'C:\path\to\workspace' --request 'Modify app.py and add input validation'
```

## Example requests

- `Create a Python file that prints Hello World.`
- `Create an HTML page with a title and a button.`
- `Read main.py`
- `Modify app.py and add input validation`

## Error handling

The agent prints clear messages when:

- Ollama is not installed or not reachable
- The selected model is missing
- The request is unclear
- The requested file does not exist
- Multiple files match the same file name
- The model returns invalid or empty output
- A path tries to escape the selected workspace
- The selected file is not readable as UTF-8 text

## Files

- `agent.py`: main terminal agent
- `README.md`: setup and usage

## Notes

- This is intentionally a simple single-agent implementation.
- It does not use memory, RAG, scheduling, or multi-agent behavior.
- The safest demo flow is to select a small test workspace and try create, read, and modify commands live.
