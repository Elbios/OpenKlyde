import json
import requests 
import os
import asyncio
import re
import base64
import random
from PIL import Image
import io
import datetime

# Set an API struct to whatever is in a JSON file to our heart's content
async def set_api(config_file):

    # Go grab the configuration file for me
    file = get_file_name("configurations", config_file)
    contents = await get_json_file(file)
    api = {}
    
    # If contents aren't none, clear the API and shove new data in
    if contents != None:
        api.update(contents)

    # Return the API
    return api

# Check to see if the API is running (pick any API)
async def api_status_check(link, headers):

    try:
        response = requests.get(link, headers=headers)
        status = response.ok
    except requests.exceptions.RequestException as e:
        await write_to_log("Error occurred: " + e +". Language model not currently running.")
        status = False

    return status

def get_file_name(directory, file_name):

    # Create the file path from name and directory and return that information
    filepath = os.path.join(directory, file_name)
    return filepath

# Read in a JSON file and spit it out, usefully or "None" if file's not there or we have an issue 
async def get_json_file(filename):

    # Try to go read the file!
    try:
        with open(filename, 'r') as file:
            contents = json.load(file)
            return contents
    # Be very sad if the file isn't there to read
    except FileNotFoundError:
        await write_to_log("File " + filename + "not found. Where did you lose it?")
        return None
    # Be also sad if the file isn't a JSON or is malformed somehow
    except json.JSONDecodeError:
        await write_to_log("Unable to parse " + filename + " as JSON.")
        return None
    # Be super sad if we have no idea what's going on here
    except Exception as e:
        await write_to_log("An unexpected error occurred: " + e)
        return None

# Write a line to the log file    
async def write_to_log(information):
    file = get_file_name("", "log.txt")
    
    # Add a time stamp to the provided error message
    current_time = datetime.datetime.now()
    rounded_time = current_time.replace(microsecond=0)
    text = str(rounded_time) + " " + information + "\n"
    
    await append_text_file(file, text)
    
# Figure out if the user is looking for an image to be generated    
def check_for_image_request(user_message):
    # Set user's message to all lowercase
    user_message = user_message.lower()
    
    # Create a pattern we'll be matching against
    pattern = re.compile('(send|create|give|generate|draw|snap|show|take|message).*?(image|picture|photo|photogragh|pic|drawing|painting|screenshot)')
    
    # Do some matching, I suppose
    result = bool(pattern.search(user_message))
    return result

async def create_prompt_for_random_message(character, bot, text_api):
    random_msg_prompt = random.choice([
        "You are bored and want to send a random message on your favorite Discord channel for attention. Write a random message as yourself, talking about what you've been up to.",
        "You are bored and want to send a random message on your favorite Discord channel for attention. Write a random message as yourself, ranting about something that irks you.",
        "You are bored and want to send a random message on your favorite Discord channel for attention. Write a random message as yourself, saying a random fact that you found interesting.",
        "You are bored and want to send a random message on your favorite Discord channel for attention. Write a random message as yourself, saying something nefarious or controversial to stir up the chat.",
    ])
    prompt = character + "\n" + random_msg_prompt + "\n"# + bot + ": "
#    random_m = "You are bored and want to send a random message on your favorite Discord channel for attention. Write a random message as yourself, talking about what you've been up to."
    #prompt = character + "\n" + random_m + bot + ": "
    stopping_strings = ["\n" + ":", bot + ":", "You:", "@Ava", "User"]
    
    data = text_api["parameters"]
    prompt = "[INST] " + prompt + " [/INST]" # for Mixtral
    data.update({"prompt": prompt})
    
    if text_api["name"] == "openai":
        data.update({"stop": stopping_strings})
    else:
        data.update({"stop_sequence": stopping_strings})

    data_string = json.dumps(data)
    return data_string

async def create_text_prompt(user_input, user, character, bot, history, reply, text_api, image_description=None):

    hint = "You are currently replying to " + user + ".\n" + "Conversation history is below:\n"
    if image_description:
        image_prompt = "[NOTE TO AI - USER MESSAGE CONTAINS AN IMAGE. IMAGE RECOGNITION HAS BEEN RUN ON THE IMAGE. PLEASE REFER TO THE IMAGE IN YOUR RESPONSE. DESCRIPTION OF THE IMAGE: " + image_description.capitalize() + "]"
        prompt = character + hint + history + reply + user + ": " + user_input + "\n" + image_prompt + "\n" + bot + ": "
    else:
        prompt = character + hint + history + reply + user + ": " + user_input + "\n" + bot + ": "
    stopping_strings = ["\n" + user + ":", user + ":", bot + ":", "You:", "@Ava", "User", "@" + user, "<|endoftext|>"]
    
    data = text_api["parameters"]
    
    if text_api["name"] == "openai":
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]
 #       data.update({"stop": stopping_strings})
        data.update({"messages" : messages})
    else:
        data.update({"prompt": prompt})
        data.update({"stop_sequence": stopping_strings})

    data_string = json.dumps(data)
    return data_string
    
async def create_image_prompt(user_input, character, text_api):

    user_input = user_input.lower()
    
    if "of" in user_input:
        subject = user_input.split('of', 1)[1]
        prompt = "Please describe the following in maximum three sentences, in vivid detail using descriptive keywords so that someone could draw that based on that description: " + subject + "\n"
    else:
        prompt = "Please describe the way you look in maximum three sentences, in vivid detail using descriptive keywords so that someone could draw you based on that description."
        
    stopping_strings = ["### Instruction:", "### Response:", "You:" ]
    
    data = text_api["parameters"]
    
    if text_api["name"] == "openai":
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]
 #       data.update({"stop": stopping_strings})
        data.update({"messages" : messages})
    else:
        data.update({"prompt": prompt})
        data.update({"stopping_strings": stopping_strings})

    data_string = json.dumps(data)
    return data_string

# Clean username before storing a context .txt file with that username
def clean_username(username):
    # Replace invalid characters with an underscore
    cleaned_username = re.sub(r'[<>:"/\\|?*]', '_', username)

    # Remove any trailing spaces or periods (as they are not allowed at the end of Windows filenames)
    cleaned_username = cleaned_username.rstrip('. ')
    return cleaned_username

# Get user's conversation history

async def get_conversation_history(message, user, lines):
    messages = []
    async for msg in message.channel.history(limit=lines):
        messages.append(msg)
    
    # Reverse the list to get messages in chronological order
    messages.reverse()

    # Create a string with the conversation history
    conversation_history = "\n".join([f"{msg.author.name}: {msg.content}" for msg in messages])
    return conversation_history
#old implementation that only got convo history with this one user, not whole channel
#async def get_conversation_history(user, lines):
#
#    user = clean_username(user)
#    file = get_file_name("context", user + ".txt")
#    
#    # Get as many lines from the file as needed
#    contents, length = await get_txt_file(file, lines)
#    
#    if contents is None:
#        contents = ""
#        
#    if length > 50:
#        await prune_text_file(file, 30)
#        
#    return contents

async def add_to_conversation_history(message, user, file):

    file = clean_username(file)
    user = clean_username(user)
    file_name = get_file_name("context", file + ".txt")
    
    content = user + ": " + message + "\n"
    
    await append_text_file(file_name, content)

# Read in however many lines of a text file (for context or other text)
# Returns a string with the contents of the file
async def get_txt_file(filename, lines):

    # Attempt to read the file and put its contents into a variable
    try:
        with open(filename, "r", encoding="utf-8") as file:  # Open the file in read mode
            contents = file.readlines()
            length = len(contents)     
            contents = contents[-lines:]

            # Turn contents into a string for easier consumption
            # I may not want to do this step. We'll see
            history_string = ''.join(contents)
            
            return history_string, length
            
    # Let someone know if the file isn't where we expected to find it.
    except FileNotFoundError:
        await write_to_log("File " + filename + " not found. Where did you lose it?")
        return None, 0
    
    # Panic if we have no idea what's going in here
    except Exception as e:
        await write_to_log("An unexpected error occurred: " + e)
        return None, 0

async def prune_text_file(file, trim_to):

    try:
        with open(file, "r", encoding="utf-8") as f:  # Open the file in read mode
            contents = f.readlines()
            contents = contents[-trim_to:]  # Keep the last 'trim_to' lines

        with open(file, "w", encoding="utf-8") as f:  # Open the file in write mode
            f.writelines(contents)  # Write the pruned lines to the file
    
    except FileNotFoundError:
        await write_to_log("Could not prune file " + file + " because it doesn't exist.")
        
# Append text to the end of a text file
async def append_text_file(file, text):

    with open(file, 'a+', encoding="utf-8") as context:
        context.write(text)
        context.close()
        
# Clean the input provided by the user to the bot!
def clean_user_message(user_input):

    # Remove the bot's tag from the input since it's not needed.
    user_input = user_input.replace("@Kobold","")

    user_input = user_input.replace("<|endoftext|>","")
    
    # Remove any spaces before and after the text.
    user_input = user_input.strip()
    
    return user_input

# Mistral-medium hallucinates some stuff in parentheses on newlines and then it hallucinates more
def truncate_from_newline_parenthesis(text):
    # This regex pattern matches an open parenthesis at the start of any line within the text
    pattern = r'^\('
    
    # Use the MULTILINE flag to ensure ^ matches the start of each line
    match = re.search(pattern, text, re.MULTILINE)
    
    # If a match is found, return the substring up to that point, else return the original string
    if match:
        return text[:match.start()]
    else:
        return text

def fix_semicolon_gemma_thing(text):
    return text.replace(": ","")

async def clean_llm_reply(message, user, bot):

    # Clean the text and prepare it for posting
    dirty_message = message.replace(bot + ":","")
    clean_message = dirty_message.replace(user + ":","")
    clean_message = clean_message.strip()
    
    clean_message = truncate_from_newline_parenthesis(clean_message)
    clean_message = fix_semicolon_gemma_thing(clean_message)
    parts = clean_message.split("#", 1)
    parts2 = parts[0].split("User1", 1) # Mistral-medium hallucination
    parts3 = parts2[0].split("@", 1) # Mistral-medium hallucination

    # Return nice and clean message
    return parts3[0]
    
# Get the current bot character in a prompt-friendly format
def get_character(character_card):

    # Your name is <name>.
    character = "Your name is " + character_card["name"] + ". "
    
    # Your name is <name>. You are a <persona>.
    character = character + "You are " + character_card["persona"] + ". "
    
    # Instructions on what the bot should do. This is where an instruction model will get its stuff.
    character = character + character_card["instructions"]

    examples = [] # put example responses here    

    # Example messages!
    character = character + " Here are examples of how you speak: " + "\n" + '\n'.join(examples) +"\n"

    return character
    
# Get the contents of a character file (which should contain everything about the character)
async def get_character_card(name):

    # Get the file name and then its contents
    file = get_file_name("characters", name)
    contents = await get_json_file(file)
    character = {}
    
    if contents != None:
        character.update(contents)

    #return the contents of the JSON file
    return character
    
# Get the list of all available characters (files in the character directory, hopefully)
def get_file_list(directory):

    # Try to get the list of character files from the directory provided. 
    try:
        dir_path = directory + "\\"
        files = os.listdir(dir_path)
    except FileNotFoundError:
        files = []
    except OSError:
        files = []

    # Return either the list of files or a blank list.
    return files

def image_from_string(image_string):

    img = base64.b64decode(image_string)
    name = "image_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
    
    with open(name, 'wb') as f:
        f.write(img)
        
    return name
