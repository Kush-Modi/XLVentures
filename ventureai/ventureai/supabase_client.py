import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()  # Load variables from .env file

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)