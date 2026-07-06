import json
import re
from pathlib import Path
from stable_whisper import load_model


# =====================================================================
# Einstellungen
# =====================================================================

AUDIO_FILE = r"G:\Media\Musizieren\Rap\Track Workspace\Kein Platz für Stärke\Kein Platz für Stärke.mp3"
LYRICS_FILE = r"G:\Media\Musizieren\Rap\Track Workspace\Kein Platz für Stärke\Lyrics RAW.txt"

PRIMARY_LANGUAGE = "de"
FILE_ENCODING = "utf-8"

MODEL = r"D:\Programming Workspace\ClaudeWorkspace\whatsapp-transscriber\models\large-v3.pt"


# =====================================================================
# Utility functions
# =====================================================================

def tokenize(text):
    return re.findall(r"\w+(?:'\w+)?", text, flags=re.UNICODE)


def srt_time(seconds):
    ms = int(round((seconds % 1) * 1000))
    total = int(seconds)
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


## =====================================================================
## EXECUTION FLOW
## =====================================================================

## Derive output filenames
language_code = f"{PRIMARY_LANGUAGE.lower()}_{PRIMARY_LANGUAGE.upper()}"
audio_path = Path(AUDIO_FILE)
base = audio_path.stem
folder = audio_path.parent
OUTPUT_JSON = f"{folder}/{base}.{language_code}.json"
OUTPUT_WORDS = f"{folder}/{base} (Karaoke).{language_code}.srt"
OUTPUT_LINES = f"{folder}/{base}.{language_code}.srt"

## Load model
print("Loading Model...")
model = load_model(MODEL)

## Load lyrics
with open(LYRICS_FILE, FILE_ENCODINGoding=FILE_ENCODING) as f: lyrics = f.read()

## Forced alignment
print("Aligning lyrics...")
result = model.align(AUDIO_FILE, text=lyrics, language=PRIMARY_LANGUAGE)

## Save JSON
print("Save JSON...")
result.save_as_json(str(OUTPUT_JSON))

## Create SRT file (word level)
print("Creating karaoke SRT file...")
result.to_srt_vtt(str(OUTPUT_WORDS), word_level=True)

## Derive segmentation and create SRT file (line level)
print("Creating regular SRT file...")
with open(OUTPUT_JSON, FILE_ENCODINGoding=FILE_ENCODING) as f: data = json.load(f)

all_words = []
for segment in data["segments"]:
    for w in segment.get("words", []):
        word = w["word"].strip()
        if word:
            all_words.append({
                "word": word,
                "start": w["start"],
                "end": w["end"]
            })

with open(LYRICS_FILE, FILE_ENCODINGoding=FILE_ENCODING) as f:
    lyric_lines = [
        line.rstrip()
        for line in f
        if line.strip()
    ]

word_index = 0
with open(OUTPUT_LINES, "w", FILE_ENCODINGoding=FILE_ENCODING) as out:
    counter = 1
    for line in lyric_lines:
        tokens = tokenize(line)
        if not tokens: continue
        if word_index + len(tokens) > len(all_words): raise RuntimeError("Mismatch found between JSON content and given lyrics!")
        first = all_words[word_index]
        last = all_words[word_index + len(tokens) - 1]
        out.write(f"{counter}\n")
        out.write(f"{srt_time(first['start'])} --> {srt_time(last['end'])}\n")
        out.write(line + "\n\n")
        word_index += len(tokens)
        counter += 1

print()
print("DONE!")
print("JSON:\t", OUTPUT_JSON)
print("Karaoke:\t", OUTPUT_WORDS)
print("Regular:\t", OUTPUT_LINES)
