# Codevid

![Codevid Logo](assets/logo.svg)

**Turn your automated tests into professional video tutorials.**

Codevid is a CLI tool that uses AI to convert your existing Python Playwright tests into narrated, captioned video tutorials. It analyzes your test code, generates a natural language script, records the execution, and automatically edits everything into a polished video.

## 🎬 How It Works

[demo2.webm](https://github.com/user-attachments/assets/dc3540b3-edc7-4699-944e-1d5ede65fbd6)

### Generated Tutorial

Here's the result - a fully narrated video tutorial generated from the test above:

https://github.com/user-attachments/assets/de1d647b-527b-4c66-a46b-7b86247c345c

## 🚀 Features

*   **Automated Scriptwriting**: Uses LLMs (OpenAI/Anthropic) to explain *why* an action is happening, not just *what* is happening.
*   **Real Execution**: Records your actual app in a browser to ensure the video matches reality.
*   **AI Voiceovers**: Integrated Text-to-Speech (OpenAI/Edge TTS) for professional narration.
*   **Smart Editing**: Automatically synchronizes video speed with audio narration and adds captions.
*   **Stable Sync**: Keeps narration aligned even when multiple narration segments map to one test step.

## 📋 Prerequisites

*   **Python 3.11+**
*   **OpenAI API Key**: Codevid requires access to an LLM to generate the narration script.

## 🛠️ Installation

1.  **Install Codevid** (assuming it is available via pip or from source):
    ```bash
    pip install codevid
    ```

2.  **Install Playwright Browsers**:
    ```bash
    playwright install chromium
    ```

## 🔑 Configuration

You **must** provide your OpenAI API key for the tool to function.

```bash
export OPENAI_API_KEY="sk-..."
```

*(Alternatively, you can configure Anthropic/Claude keys if you prefer that provider in the config).*

## ⚡ Quick Start

1.  **Initialize a project** (optional, creates a `codevid.yaml` config file):
    ```bash
    codevid init
    ```

2.  **Generate a video**:
    Pass your Playwright test file to the `generate` command.

    ```bash
    codevid generate examples/test_login.py -o login_tutorial.mp4
    ```

## 📖 Usage Examples

### Basic Generation
Uses default settings (Anthropic/Edge TTS if not configured otherwise) to generate a video.
```bash
codevid generate tests/my_test.py
```

### Using OpenAI for Everything
Specify the LLM and TTS provider explicitly via CLI flags.
```bash
codevid generate tests/my_test.py \
    --llm openai \
    --tts openai \
    --voice alloy \
    --output tutorial.mp4
```

### Preview Script Only
Want to see what the AI will say before recording? Use preview mode.
```bash
codevid preview tests/my_test.py
```

### List Available Voices
See which voices are available for your chosen provider.
```bash
codevid list-voices openai
```

## ⚠️ Current Limitations

*   **Framework Support**: Currently, Codevid **only supports Python Playwright** tests.
*   **Structure**: Tests must be written as standard functions or Pytest functions (e.g., `def test_example(page):`).

## 📄 License

[MIT](LICENSE)
