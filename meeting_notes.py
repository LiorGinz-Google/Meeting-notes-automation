#################################################################################################
# Developer: Lior (Leo) Ginzberg - liorginz@google.com
# Script Name: meeting_notes.py
# Purpose: Streamline cross-organization meeting notes by summarizing them and consolidating them 
#          into a single, easily managed document, for efficient progress tracking and ensure 
#          effective action item management. The current process is completely manual
# Potential Savings: 50 (team members) * 2 (meeting a day) * 15 (minutes to manually add notes) =
#                    1,500 minutes (Day) = 25 hours (Day) = 762 hours (Month) = 3.8 (Resources monthly)
# Parameters: none
# Execution: nohup meeting_notes.py & (to run in the background) or python meeting_notes.py
# Prerequisits:
#   1. create the following 3 Google drive folders:
#       1.1 Root folder. You can call it in any name
#       1.2 Archive folder (Under the root folder). You can call it in any name
#       1.3 Source folder (Under the root folder). You can call it in any name
#   2. Create an empty Google document in the source folder. Give it a meaningful name such as
#      Account/Group Name - Meeting Notes
#   3. Create a Gemini API key.
#       3.1 Go to https://aistudio.google.com/
#       3.2 Get API Key
#       3.3 Create API Key
#       3.4 Search and select your project and create key in existing project
#   4. Populate the following in the configuration section of the script: 
#       4.1 folder_id should be populated with the ID of the 1.3 folder (Source folder) 
#       4.2 archive_folder_id should be populated with the ID of the 1.2 folder (Archive folder)
#       4.4 archive_folder_name should be populated with the full name of the 1.2 folder (Archive folder)
#       4.5 destination_doc_id should be populated with the ID of the document created in step 2 above
#       4.6 GEMINI_API_KEY should be populated with the key that you created in 3.4
#    5. install any of the libraries referred to at the beginning of the script, if not yet done
# Flow:
#   1. Educate your Org' to use the "Take notes with Gemini" for every meeting using Google meet 
#      and that "Allow transcribe the meeting" checkbox is checked
#   2. At the end of every call the meeting owner will receive an email, from Google Meet, 
#      with 3 attachments
#   3. The transcribe attachment should be saved in the folder you created in the above Prerequisits 
#      section in step 1.3 above
#   4. This script is running in the background and will automatically pick any valid file that is
#      placed in the folder
#   5. The script will do the following in a loop:
#       5.1 Read all the files from the source folder
#       5.2 Get the content of each file
#       5.3 Leverage Gemini to summarize the content into 5 sections (meeting subject, meeting date, 
#           meeting participants,main details discussed and action items)
#       5.4 Write the summary into the meeting notes document you created in the above Prerequisits
#           section in step 2 above
#       5.5 Archive the file in the folder you created in the above Prerequisits section in step 
#           in step 1.2     
# Revisions: 
#   1. Initial revision. January 2024 & Feabruary 2025
# Limitations:
#   1. Will work for any file that is supported by the model used for summarization 
#      (Currently: gemini-2.0-flash)
#   2. Meetings that are not using Google Meet will require the meeting owner to share the 
#      transcript file with his Google counterpart, so that he can follow this flow. The file
#      will need to be converted to a Gogole doc file or the code will need to be enhanced to support
#      the new file format
#   3. Anything that needs to be added on top of the meeting notes (Screenshot, comments, 
#      rephrasing, etc') will have to be done manually   
##################################################################################################

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth import default
from google.cloud import aiplatform
import requests
import pathlib
from google import genai
import io
import os
import json
import re
import time

#Configuration
#Folder and file Information
#The folder or file ID can be extracted from the folder/file url
#Example: https://docs.google.com/document/d/18s4M5Iv5RdG2liNnmP1U_okecPxh73h_Hbt1M_VpFlM/edit?resourcekey=0-QgQMlM77fCA3IiE52Bjthg&tab=t.0#heading=h.f25wc8qd2cx9
#The ID is the string between d/ and /edit?
folder_id = '' #The folder to read transcripts from
archive_folder_id = ''
archive_folder_name = '' "the full link to the archive folder
destination_doc_id = '' #The meeting notes file

#Gemini API / End point information
GEMINI_API_KEY = ""  # Replace with your actual API key
#GEMINI_API_ENDPOINT = "https://api.gemini.com/v1/summarize" # Replace with Gemini 1.5 Pro endpoint

#Initializing credentials with the credentials of the user running the script and creating a GenAI client 
creds, project = default()
client = genai.Client(api_key=GEMINI_API_KEY)

#Create a service object that can interact with the Google Drive API for folders and files
drive_service = build('drive', 'v3', credentials=creds)
docs_service = build('docs', 'v1', credentials=creds)

#Functions
#Retrieves a list of file IDs for all files within a specified Google Drive folder
def get_file_ids_in_folder(folder_id, creds):

    #drive_service = build('drive', 'v3', credentials=creds)

    file_ids = []
    query = f"'{folder_id}' in parents"
    page_token = None
    while True:
        response = drive_service.files().list(q=query,
                                              spaces='drive',
                                              fields='nextPageToken, files(id, name)',
                                              pageToken=page_token).execute()
        for file in response.get('files',):
            print(F'Found file: {file.get("name")}, {file.get("id")}')
            file_ids.append(file.get('id'))
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break

    return file_ids

#Read the content of a Google dcoument file
def read_google_doc(doc_id, creds):
    #drive_service = build('drive', 'v3', credentials=creds)
    #docs_service = build('docs', 'v1', credentials=creds)

    # Download the Google Doc as a text file
    request = drive_service.files().export_media(fileId=doc_id, mimeType='text/plain')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()

    text = fh.getvalue().decode('utf-8')
    return text


#Write content to a Google dcoument file
def write_to_google_doc(doc_id, summary, creds):
    #docs_service = build('docs', 'v1', credentials=creds)

    print(f"SUMMARY: {summary}\n")

    requests = [
        {
            'insertText': {
                'location': {
                    'index': 1,  # Insert at the beginning
                },
                'text': '**NEW ENTRY**:\n' + summary + '\n' * 3 
            }
        }
    ]

    result = docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
    return result

def main():

    #Get all pending files, from source folder, that are waiting to be processed (summarized)
    file_ids = get_file_ids_in_folder(folder_id, creds)

    print("\nFile IDs in folder:")
    
    for file_id in file_ids:
        if file_id != destination_doc_id:
            print(f"{file_id} is being processed...")
            
            #Get the text content of the file
            doc_text = read_google_doc(file_id, creds)

            #Call Gemini to summarize the file
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=[
                    'summarize this file and provide the following sections: \
                    meeting subject, meeting date, meeting participants, main details discussed and action items. \
                    The meeting participants, main details discussed and action items should be presented in bullets. \
                    The bullets should not have running over sentences. Do not add any text to the output besides the summary results', 
                    doc_text
                ]
            )
            
            #Perform basic formatting of the Gemini summary 
            formatted_text = response.text.replace("**", "").replace("Here's a summary of the meeting, formatted as requested:","")
            
            #Write the Gemini Summary to the meeting notes document
            write_to_google_doc(destination_doc_id, formatted_text, creds)

            print(f"{file_id} has been fully processed")

            #Archive the fully processed file
            file = drive_service.files().update(fileId=file_id,
                                             addParents=archive_folder_id,
                                             removeParents=folder_id,
                                             fields='id, parents').execute()

            print(f"{file_id} has been archived in {archive_folder_name} \n")


if __name__ == '__main__':
    while True:
      main()
      time.sleep(600)

