import requests
from bs4 import BeautifulSoup
import json
import time
import base64
import uuid
import hashlib
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os

# AnkiConnect URL
ANKI_CONNECT_URL = 'http://localhost:8765'

# VocalWare credentials
API_ID = os.getenv('VW_API_ID')
ACCOUNT_ID = os.getenv('VW_ACCOUNT_ID')
SECRET_PHRASE = os.getenv('VW_SECRET_PHRASE')

# Function to get cards from a specific deck
def get_cards(deck_name):

    payload = {
        "action": "findCards",
        "version": 6,
        "params": {
            "query": f"deck:{deck_name}"
        }
    }
    response = requests.post(ANKI_CONNECT_URL, json=payload).json()
    return response['result']

# Function to get note details for cards
def get_notes(cards):
    payload = {
        "action": "cardsInfo",
        "version": 6,
        "params": {
            "cards": cards
        }
    }
    response = requests.post(ANKI_CONNECT_URL, json=payload).json()
    return response['result']

# Function to add TTS audio to a note
def add_tts_to_note(note_id, audio_file_name):
    payload = {
        "action": "updateNoteFields",
        "version": 6,
        "params": {
            "note": {
                "id": note_id,
                "fields": {
                    "Audio": f"[sound:{audio_file_name}]"
                }
            }
        }
    }
    response = requests.post(ANKI_CONNECT_URL, json=payload).json()
    if response.get('error') is not None:
        print(f"Error updating note {note_id}: {response['error']}")

# Function to get TTS audio URL from Cambridge Dictionary
def get_cambridge_tts_url(word):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

    # Replace spaces with hyphens for the search URL
    formatted_word = word.replace(' ', '-')
    
    url = f'https://dictionary.cambridge.org/dictionary/english/{formatted_word}'
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    audio_tag = soup.find('source', {'type': 'audio/mpeg'})
    if audio_tag and 'src' in audio_tag.attrs:
        return "https://dictionary.cambridge.org{}".format(audio_tag['src'])
    
    return None

# Function to get TTS audio URL from VocalWare
def get_vocalware_tts_url(word):
    base_url = 'https://www.vocalware.com/tts/gen.php'
    params = {
        'EID': 3,  # English UK, Hugh, Adult Male
        'LID': 1,  # Language ID
        'VID': 5,  # Voice ID
        'TXT': word,
        'ACC': ACCOUNT_ID,
        'API': API_ID,
    }
    

    # Generate the hash
    hash_string = (
    str(params['EID']) +
    str(params['LID']) +
    str(params['VID']) +
    str(params['TXT']) + 
    str(params['ACC']) + 
    str(params['API']) + 
    SECRET_PHRASE  # This should NOT be URL-encoded
    )

    params['CS'] = hashlib.md5(hash_string.encode()).hexdigest()
    
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        return response.url
    return None

# Function to download audio file from URL with retries and User-Agent
def download_audio(url, file_name):
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    try:
        response = session.get(url, headers=headers)
        response.raise_for_status()
        with open(file_name, 'wb') as file:
            file.write(response.content)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url}: {e}")
        return False

# Function to upload audio file to Anki and get the correct file name
def upload_audio_to_anki(file_name):
    try:
        with open(file_name, 'rb') as file:
            data = file.read()
        b64_data = base64.b64encode(data).decode('utf-8')
        payload = {
            "action": "storeMediaFile",
            "version": 6,
            "params": {
                "filename": file_name,
                "data": b64_data
            }
        }
        response = requests.post(ANKI_CONNECT_URL, json=payload).json()
        if response.get('error') is not None:
            print(f"Error uploading file {file_name}: {response['error']}")
            return None
        return response['result']
    except Exception as e:
        print(f"Exception uploading file {file_name}: {e}")
        return None

def main(deck_name):
    cards = get_cards(deck_name)
    notes = get_notes(cards)
    
    processed_words = set()

    for note in notes:
        note_id = note['note']
        word = note['fields']['Word']['value']
        
        # Check if Audio field already has a value
        audio_field = note['fields'].get('Audio', {}).get('value', '')
        if audio_field.strip():
            print(f"[-] Audio already exists for word: {word}, skipping...")
            continue
        else:
            print(f"[+] Download audio file for word '{word}'...")

        # Check if the word has already been processed
        if word in processed_words:
            print(f"[-] Word '{word}' already processed, skipping...")
            continue

        # Use Cambridge by default then go to VocalWare 
        audio_url = get_cambridge_tts_url(word)
        if not audio_url:
            audio_url = get_vocalware_tts_url(word)
        
        if audio_url:
            # Generate a UUID for the file name
            unique_filename = f"vocalware-{uuid.uuid4()}.mp3"
            if download_audio(audio_url, unique_filename):
                audio_file_name = upload_audio_to_anki(unique_filename)
                if audio_file_name:
                    add_tts_to_note(note_id, audio_file_name)
                    processed_words.add(word)
                else:
                    print(f"[-] Failed to upload audio for word: {word}")
        else:
            print(f"[-] No audio found for word: {word}")

if __name__ == "__main__":
    main("Test")
