import streamlit as st
from langchain.document_loaders import (
    PyPDFLoader,
    TextLoader,
    CSVLoader,
    PyMuPDFLoader,
    UnstructuredFileLoader,
)
import os
import tempfile
import uuid
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from newspaper import Article
import validators
import pandas as pd

load_dotenv()

class DocumentProcessor:
    def __init__(self):
        self.pages = []
        self.processed_urls = set()
        self.counter = 0  # Universal counter for all inputs

    def ingest_documents(self):
        st.header("Upload Documents/Media")

        uploaded_files = st.file_uploader("Choose files", type=["pdf", "docx", "doc", "pptx", "ppt", "txt", "csv"], accept_multiple_files=True)

        urls = st.text_input("Enter URLs separated by comma")
        if urls:
            urls = urls.split(",")
            for url in urls:
                url = url.strip()
                if url and url not in self.processed_urls:
                    if validators.url(url):
                        self.process_url(url)
                    else:
                        st.error(f"Invalid URL: {url}")

        direct_input = st.text_area("Or paste your text directly here")
        if direct_input:
            self.process_direct_input(direct_input)

        if uploaded_files:
            for uploaded_file in uploaded_files:
                self.process_file(uploaded_file)

        if self.pages:
            st.write(f"Total pages/content processed: {len(self.pages)}")
            for i, page in enumerate(self.pages):
                st.write(f"Content {i + 1}:\n{page[:200]}...")  # Display a preview of each content
        else:
            st.write("No files or URLs processed.")

    def process_url(self, url):
        try:
            if "youtube.com" in url or "youtu.be" in url:
                video_id = self.extract_youtube_video_id(url)
                if video_id:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id)
                    total_duration = transcript[-1]['start'] + transcript[-1]['duration']
                    
                    st.write(f"Video duration: {self.format_time(total_duration)}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        start_time = self.time_input("Start time", total_duration, f"start_{self.counter}")
                    with col2:
                        end_time = self.time_input("End time", total_duration, f"end_{self.counter}", start_time)
                    
                    text = " ".join([entry["text"] for entry in transcript if start_time <= entry["start"] <= end_time])
                else:
                    st.error(f"Could not extract video ID from URL: {url}")
                    return
            else:
                article = Article(url)
                article.download()
                article.parse()
                paragraphs = article.text.split('\n\n')
                selected_paragraphs = st.multiselect(f"Select paragraphs to include from {url}", 
                                                     options=range(len(paragraphs)), 
                                                     format_func=lambda x: paragraphs[x][:100] + "...",
                                                     key=f"paragraphs_{self.counter}")
                text = "\n\n".join([paragraphs[i] for i in selected_paragraphs])

            self.processed_urls.add(url)
            st.success(f"Successfully processed URL: {url}")
            self.pages.append(text)
            self.counter += 1
        except Exception as e:
            st.error(f"Error processing URL {url}: {str(e)}")

    def process_file(self, uploaded_file):
        try:
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            unique_id = uuid.uuid4().hex
            original_name, _ = os.path.splitext(uploaded_file.name)
            temp_file_name = f"{original_name}_{unique_id}{file_extension}"
            temp_file_path = os.path.join(tempfile.gettempdir(), temp_file_name)

            with open(temp_file_path, 'wb') as f:
                f.write(uploaded_file.getvalue())

            loader_map = {
                ".pdf": PyPDFLoader,
                ".docx": PyMuPDFLoader,
                ".doc": PyMuPDFLoader,
                ".pptx": PyMuPDFLoader,
                ".ppt": PyMuPDFLoader,
                ".txt": TextLoader,
                ".csv": CSVLoader
            }

            loader_class = loader_map.get(file_extension, UnstructuredFileLoader)
            loader = loader_class(temp_file_path)

            if file_extension == ".pdf":
                pages = loader.load()
                start_page = st.number_input(f"Start page for {uploaded_file.name}", 
                                             min_value=1, max_value=len(pages), key=f"start_page_{self.counter}")
                end_page = st.number_input(f"End page for {uploaded_file.name}", 
                                           min_value=start_page, max_value=len(pages), key=f"end_page_{self.counter}")
                self.pages.extend([page.page_content for page in pages[start_page-1:end_page]])
            elif file_extension == ".csv":
                df = pd.read_csv(temp_file_path)
                selected_columns = st.multiselect(f"Select columns for {uploaded_file.name}", 
                                                  options=df.columns, key=f"columns_{self.counter}")
                start_row = st.number_input(f"Start row for {uploaded_file.name}", 
                                            min_value=0, max_value=len(df), key=f"start_row_{self.counter}")
                end_row = st.number_input(f"End row for {uploaded_file.name}", 
                                          min_value=start_row, max_value=len(df), key=f"end_row_{self.counter}")
                selected_df = df.loc[start_row:end_row, selected_columns]
                self.pages.append(selected_df.to_string())
            elif file_extension in [".pptx", ".ppt"]:
                pages = loader.load()
                selected_slides = st.multiselect(f"Select slides for {uploaded_file.name}", 
                                                 options=range(1, len(pages)+1), key=f"slides_{self.counter}")
                self.pages.extend([pages[i-1].page_content for i in selected_slides])
            else:
                pages = loader.load()
                self.pages.extend([page.page_content for page in pages])

            os.unlink(temp_file_path)
            st.success(f"Successfully processed file: {uploaded_file.name}")
            self.counter += 1
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {str(e)}")

    def process_direct_input(self, text):
        highlighted_text = st.text_area("Highlight specific parts (copy-paste from above)", 
                                        text, key=f"highlight_{self.counter}")
        self.pages.append(highlighted_text)
        self.counter += 1

    def time_input(self, label, max_duration, key, min_time=0):
        hours = int(max_duration // 3600)
        minutes = int((max_duration % 3600) // 60)
        seconds = int(max_duration % 60)

        if hours > 0:
            h = st.number_input(f"{label} (hours)", min_value=0, max_value=hours, key=f"{key}_hours")
            m = st.number_input(f"{label} (minutes)", min_value=0, max_value=59, key=f"{key}_minutes")
            s = st.number_input(f"{label} (seconds)", min_value=0, max_value=59, key=f"{key}_seconds")
            total_seconds = h * 3600 + m * 60 + s
        elif minutes > 0:
            m = st.number_input(f"{label} (minutes)", min_value=0, max_value=minutes, key=f"{key}_minutes")
            s = st.number_input(f"{label} (seconds)", min_value=0, max_value=59, key=f"{key}_seconds")
            total_seconds = m * 60 + s
        else:
            total_seconds = st.number_input(f"{label} (seconds)", min_value=0, max_value=seconds, key=f"{key}_seconds")

        return max(min_time, min(total_seconds, max_duration))

    @staticmethod
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        elif minutes > 0:
            return f"{minutes:02d}:{seconds:02d}"
        else:
            return f"{seconds:02d} seconds"

    @staticmethod
    def extract_youtube_video_id(url):
        if "youtube.com" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be" in url:
            video_id = url.split("/")[-1]
        else:
            video_id = None
        if video_id and "?" in video_id:
            video_id = video_id.split("?")[0]
        return video_id

if __name__ == "__main__":
    processor = DocumentProcessor()
    processor.ingest_documents()