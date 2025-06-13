# Import necessary libraries
import argparse
import queue
import sys
import json
import threading
import time # For display delay logic
import os
import io # Re-added for in-memory audio stream

# --- GUI IMPORT ---
import tkinter as tk
from tkinter import scrolledtext 

# --- VOSK & SOUNDDEVICE IMPORTS ---
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# --- GEMINI IMPORTS & SETUP ---
import google.generativeai as genai
from dotenv import load_dotenv
from collections import deque

# --- TTS IMPORTS (EdgeTTS) ---
import asyncio
import edge_tts
import edge_tts.exceptions # For specific error handling
import aiohttp.client_exceptions # For specific error handling

# --- Pydub import for audio conversion (playback part removed) ---
from pydub import AudioSegment

# --- NumPy import for audio data manipulation ---
import numpy as np

# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# Configure the Gemini API with your key
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("Error: GEMINI_API_KEY not found. Please create a .env file.")
    sys.exit(1) 

# --- GLOBAL VARIABLES (as per original script) ---
audio_queue = queue.Queue()
stop_event = threading.Event() 
conversation_history = deque(maxlen=5) 

tagalog_text_var = None
cebuano_text_var = None

translated_text_display_end_time = 0.0 
TRANSLATION_DISPLAY_DURATION = 2.5  

# --- NEW TTS FUNCTION using edge-tts (Modified for sounddevice playback & retry) ---
async def amain_speak(text: str, voice: str) -> None:
    """
    Main asynchronous function to stream TTS from edge-tts, collect audio, and play with sounddevice.
    Includes a retry mechanism for fetching audio and checks stop_event frequently.
    """
    if not text.strip() or stop_event.is_set():
        return

    max_retries = 2
    retry_delay = 1 

    for attempt in range(max_retries):
        if stop_event.is_set():
            print("TTS process aborted by stop_event before attempt.")
            return
        try:
            communicate = edge_tts.Communicate(text, voice)
            audio_buffer = io.BytesIO()

            async for chunk in communicate.stream():
                if stop_event.is_set():
                    print("TTS stream fetch interrupted by stop_event.")
                    return
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            
            if stop_event.is_set():
                print("TTS process aborted by stop_event after stream fetch.")
                return

            if audio_buffer.getbuffer().nbytes == 0:
                if not stop_event.is_set():
                    print(f"No audio data received from edge-tts for: '{text}' on attempt {attempt + 1}.")
                if attempt < max_retries - 1:
                    if stop_event.is_set(): return
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    return

            audio_buffer.seek(0)
            audio_segment = AudioSegment.from_file(audio_buffer, format="mp3")
            samples_array = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)
            
            if audio_segment.channels > 1:
                samples_array = samples_array.reshape((-1, audio_segment.channels))

            def play_audio_with_sounddevice(s_array, s_rate): # Removed s_channels from parameters
                if stop_event.is_set(): # Check before starting playback
                    print("Playback aborted by stop_event before sd.play.")
                    return
                try:
                    # Let sounddevice infer channels from the array shape
                    sd.play(s_array, samplerate=s_rate) 
                    sd.wait() 
                except Exception as e_sd:
                    if not stop_event.is_set():
                        print(f"Error during sounddevice playback: {e_sd}")
            
            if not stop_event.is_set():
                # Pass only s_array and s_rate to the thread function
                await asyncio.to_thread(play_audio_with_sounddevice, samples_array, audio_segment.frame_rate)
            else:
                print("TTS process aborted by stop_event before playback thread.")
            
            return 

        except (edge_tts.exceptions.NoAudioReceived, aiohttp.client_exceptions.ClientConnectionError) as e_tts:
            if not stop_event.is_set():
                print(f"EdgeTTS Error (attempt {attempt + 1}/{max_retries}): {e_tts}")
            if attempt < max_retries - 1:
                if stop_event.is_set(): return
                await asyncio.sleep(retry_delay)
            else:
                if not stop_event.is_set():
                    print(f"Failed to fetch/play TTS after {max_retries} attempts for text: '{text}'")
                return
        except Exception as e_general:
            if not stop_event.is_set():
                print(f"Unexpected error in TTS processing or playback: {e_general}")
            return


def speak_text(text, voice_name):
    if not text or stop_event.is_set():
        return
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(amain_speak(text, voice_name))
        loop.close()
    except RuntimeError as e:
        if not stop_event.is_set():
             print(f"RuntimeError calling speak_text (event loop issue): {e}")
    except Exception as e:
        if not stop_event.is_set():
            print(f"Unexpected error in speak_text: {e}")


def start_speak_thread(text, voice_name): 
    if text and not stop_event.is_set(): 
        tts_thread = threading.Thread(target=speak_text, args=(text, voice_name))
        tts_thread.daemon = True 
        tts_thread.start()

def translate_text_with_gemini(text, history, target_language):
    if not text.strip():
        return ""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest') 
        formatted_history = "\n".join(f"- {s}" for s in history)
        prompt = (
            f"You are an expert, low-latency translation engine specializing in Philippine languages. Your task is to translate Tagalog to {target_language} (Bisaya).\n\n"
            f"**Core Directives:**\n"
            f"1.  **Translate Accurately:** Convey the full context, nuance, and intent, not just the literal words.\n"
            f"2.  **Use Context:** Leverage the 'Conversation History' to inform the translation of the 'New Text to Translate'.\n"
            f"3.  **Preserve Tone:** Match the formality and tone (e.g., casual, formal, slang) of the original Tagalog text.\n\n"
            f"**Rules for Handling Input:**\n"
            f"-   **Taglish (Tagalog/English):** If the input contains English words, integrate them naturally into the Cebuano translation as a native speaker would.\n"
            f"-   **Non-Tagalog/Nonsense:** If the 'New Text to Translate' is not Tagalog, is unintelligible, or is just a filler sound (e.g., 'uhm', 'ehem'), return an empty string. Do not attempt to translate it.\n\n"
            f"**Strict Output Format:**\n"
            f"-   You MUST return ONLY the final Cebuano translation.\n"
            f"-   DO NOT add any extra words, explanations, labels, or quotation marks. The output must be clean text, ready for a text-to-speech engine.\n\n"
            f"--- CONTEXT & TASK ---\n"
            f"Conversation History (Tagalog):\n{formatted_history}\n\n"
            f"New Text to Translate (Tagalog):\n'{text}'\n\n"
            f"Cebuano Translation:"  # This primes the model to provide only the translation
        )
        response = model.generate_content(prompt)
        translated_text = response.text.strip() 
        return translated_text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"[Gemini Error] {text}"

def audio_transcription_thread(model_path, device_id, root_window):
    global conversation_history, translated_text_display_end_time
    global tagalog_text_var, cebuano_text_var

    target_language = "Cebuano"
    tts_voice = "fil-PH-BlessicaNeural"

    try:
        vosk_model = Model(model_path=model_path)
        device_info = sd.query_devices(device_id, 'input')
        samplerate = int(device_info['default_samplerate'])
        recognizer = KaldiRecognizer(vosk_model, samplerate)
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(status, file=sys.stderr)
            if not stop_event.is_set(): # Check before putting to prevent filling queue during shutdown
                audio_queue.put(bytes(indata)) 

        print("Audio thread started. Listening...")
        with sd.RawInputStream(samplerate=samplerate, blocksize=8000, device=device_id,
            dtype='int16', channels=1, callback=audio_callback):
            while not stop_event.is_set(): 
                try:
                    # Use timeout to make the loop responsive to stop_event
                    data = audio_queue.get(timeout=0.1) 
                except queue.Empty:
                    # If queue is empty, loop again to check stop_event
                    continue 
                
                if stop_event.is_set(): # Double check after potentially waking from queue.get
                    break

                current_time = time.time()

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    raw_text = result.get('text', '').strip()
                    
                    if raw_text:
                        if tagalog_text_var: tagalog_text_var.set(raw_text) 
                        
                        translated_text_result = translate_text_with_gemini(raw_text, conversation_history, target_language)
                        
                        if cebuano_text_var: cebuano_text_var.set(translated_text_result)
                        translated_text_display_end_time = time.time() + TRANSLATION_DISPLAY_DURATION
                        
                        conversation_history.append(raw_text)
                        
                        if not stop_event.is_set(): # Check before starting new thread
                            start_speak_thread(translated_text_result, tts_voice) 
                        
                    else: 
                        if current_time > translated_text_display_end_time:
                            if tagalog_text_var: tagalog_text_var.set("")
                            if cebuano_text_var: cebuano_text_var.set("")
                else: 
                    partial_result = json.loads(recognizer.PartialResult())
                    partial_text = partial_result.get('partial', '').strip()
                    if tagalog_text_var: tagalog_text_var.set(partial_text) 
                    
                    if current_time > translated_text_display_end_time: 
                        if cebuano_text_var: cebuano_text_var.set("")
            
    except Exception as e:
        if not stop_event.is_set(): # Only print if not part of intentional shutdown
            print(f"Error in audio thread: {e}") 
    finally:
        print("Audio thread finished.")
        # Removed root_window.after(100, root_window.quit) 
        # on_closing handles Tkinter shutdown more gracefully.

def create_gui(root, args_model, args_device):
    global tagalog_text_var, cebuano_text_var

    root.title("Live Translator with TTS (Tagalog to Cebuano)") 
    root.geometry("600x250") 

    tagalog_text_var = tk.StringVar(root)
    cebuano_text_var = tk.StringVar(root)

    label_font = ("Arial", 12) 
    text_font = ("Arial", 11)  
    padding = {'padx': 10, 'pady': 5} 

    tk.Label(root, text="Tagalog (Input):", font=label_font).pack(anchor='w', **padding)
    tagalog_label = tk.Label(root, textvariable=tagalog_text_var, font=text_font, wraplength=580, justify='left', anchor='nw', height=4, relief="sunken", bd=1)
    tagalog_label.pack(fill='x', expand=False, **padding)

    tk.Label(root, text="Cebuano (Translation):", font=label_font).pack(anchor='w', **padding)
    cebuano_label = tk.Label(root, textvariable=cebuano_text_var, font=text_font, wraplength=580, justify='left', anchor='nw', height=4, relief="sunken", bd=1, fg="blue")
    cebuano_label.pack(fill='x', expand=False, **padding)

    quit_button = tk.Button(root, text="Quit", command=lambda: on_closing(root), font=label_font, bg="salmon", fg="white") 
    quit_button.pack(pady=10)
    
    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root))

    audio_thread = threading.Thread(target=audio_transcription_thread, args=(args_model, args_device, root))
    audio_thread.daemon = True
    audio_thread.start()

def on_closing(root): 
    print("Closing application...")
    if not stop_event.is_set():
        stop_event.set()
    # Give threads a moment to react to stop_event before destroying window
    root.after(300, root.destroy) # Slightly increased delay for thread cleanup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time GUI speech translator with TTS.") 
    parser.add_argument(
        "-m", 
        "--model", 
        type=str, 
        default="vosk-model-tl-ph-generic-0.6", 
        help="Path to VOSK model"
    )
    parser.add_argument(
        "-d", 
        "--device", 
        type=int,
        default=None, 
        help="Input audio device ID"
    )
    args = parser.parse_args()

    root = tk.Tk()
    create_gui(root, args.model, args.device)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Keyboard interrupt received.")
        on_closing(root) 
    finally:
        if not stop_event.is_set(): # Ensure stop_event is set if loop exited some other way
            print("Main loop exited, ensuring stop_event is set.")
            stop_event.set()
        print("Application exited.")
