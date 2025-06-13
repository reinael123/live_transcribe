# Real-Time Tagalog to Cebuano Translator

This application provides real-time, voice-to-voice translation from **Tagalog** to **Cebuano**. It captures audio from your microphone, transcribes it, translates the text using a powerful AI model, and then speaks the translation aloud.

## How It Works

1. **Speech-to-Text (STT):** It uses the **Vosk** library for offline transcription of spoken Tagalog.
    
2. **Translation:** The transcribed Tagalog text is sent to the **Google Gemini API** for accurate, context-aware translation into Cebuano.
    
3. **Text-to-Speech (TTS):** The resulting Cebuano text is converted back into speech using **Microsoft Edge's TTS service**.
    
4. **Interface:** A simple GUI built with **Tkinter** displays the live transcription and its translation.
    

## Features

- **Live Translation:** Captures microphone audio and translates on the fly.
    
- **Voice Output:** Speaks the Cebuano translation using a natural-sounding voice.
    
- **Simple GUI:** Displays the original and translated text for clarity.
    
- **Context-Aware:** Remembers the last few sentences to improve translation accuracy.
    

## Setup Instructions

### 1. Prerequisites

- Python 3.x
    
- A microphone connected to your computer.
    

### 2. Installation

First, clone this repository or download the source code. Then, install the required Python libraries by running this command in your terminal:

```
pip install -r requirements.txt
```

_(Note: You will need to create a `requirements.txt` file listing all the imported libraries like `google-generativeai`, `vosk`, `sounddevice`, `edge-tts`, `pydub`, `numpy`, and `python-dotenv`.)_

### 3. Google Gemini API Key

You need an API key from Google to use the translation service.

1. Obtain an API key from the [Google AI Studio](https://aistudio.google.com/app/apikey "null").
    
2. Create a file named `.env` in the same directory as the script.
    
3. Add your API key to the `.env` file like this:
    
    ```
    GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```
    

### 4. Vosk Speech Recognition Model

The application requires a language model for Vosk to understand Tagalog.

1. Download the [Tagalog model](https://alphacephei.com/vosk/models "null") (look for "vosk-model-tl-ph...").
    
2. Unzip the file.
    
3. Place the resulting model folder (e.g., `vosk-model-tl-ph-generic-0.6`) in the same directory as your Python script.
    

## How to Run

Once the setup is complete, you can run the application from your terminal with this command:

```
python your_script_name.py
```

The application window will appear, and it will start listening for Tagalog speech immediately. Speak into your microphone, and you will see the transcription and hear the Cebuano translation.

## Customization

### Changing the Voice

You can easily change the voice used for the Text-to-Speech output.

1. Open the Python script (`your_script_name.py`).
    
2. Find the line that defines the `tts_voice` variable:
    
    ```
    tts_voice = "fil-PH-BlessicaNeural"
    ```
    
3. Replace `"fil-PH-BlessicaNeural"` with the `ShortName` of any other voice from the list of available Edge TTS voices.
    
4. You can find a complete list of voices [here](https://gist.github.com/BettyJJ/17cbaa1de96235a7f5773b8690a20462 "null").
    

**Example:** To use the male Filipino voice, change the line to:

```
tts_voice = "fil-PH-AngeloNeural"
```
